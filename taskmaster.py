#! /usr/bin/env python

import os
import re
import argparse
import textwrap
import sys


def split_with_ws(data):
    out = []
    token = ''
    in_ws = False
    for c in data.strip():
        if c in (' ', '\t'):
            in_ws = True
        elif in_ws:
            out.append(token)
            token = ''
            in_ws = False

        token += c

    if token:
        out.append(token)

    return out


class Config(dict):
    def __init__(self):
        config = {
            'todo.txt': '~/todo.txt',
        }
        filename = os.path.abspath(os.path.normpath(os.path.expanduser('~/.taskmasterrc')))
        if os.path.exists(filename):
            kv_re = re.compile(ur'^([^\s:]+)\s*:\s*(.*)$')
            with open(filename, 'r') as fp:
                for line in fp:
                    line = line.strip()
                    if line:
                        match = kv_re.match(line)
                        if match:
                            config[match.group(0)] = match.group(1) or None
        super(Config, self).__init__(**config)


class Task(object):
    ws_re = re.compile(ur'\s+')
    date_re = re.compile(ur'^\d{4}-\d{2}-\d{2}')

    def __init__(self, description, completed=False, priority=None, created_at=None, completed_at=None, projects=None, contexts=None, tags=None, id=None, parse_description=False):
        self.description = description
        self.completed = completed
        self.priority = priority
        self.created_at = created_at
        self.completed_at = completed_at
        self.projects = projects or []
        self.contexts = contexts or []
        self.tags = tags or {}
        self.id = id

        if parse_description:
            d_desc, d_projects, d_contexts, d_tags = self.parse_description(self.description)
            self.description = d_desc
            self.projects += d_projects
            self.contexts += d_contexts
            self.tags.update(d_tags)

    @classmethod
    def parse_description(self, description):
        new_description = []
        projects = []
        contexts = []
        tags = {}

        for candidate in split_with_ws(description):
            if candidate.startswith('+') and len(candidate.strip()) > 1:
                projects.append(candidate[1:].strip())
            elif candidate.startswith('@') and len(candidate.strip()) > 1:
                contexts.append(candidate[1:].strip())
            elif ':' in candidate and len(candidate.strip()) > 1:
                k, v = candidate.strip().split(':', 1)
                tags[k] = v
            else:
                new_description.append(candidate)

        return ''.join(new_description).strip(), projects, contexts, tags

    @classmethod
    def parse(self, line, **kwargs):
        args = {
            'description': None,
            'completed': False,
            'priority': None,
            'created_at': None,
            'completed_at': None,
            'projects': [],
            'contexts': [],
            'tags': {},
        }

        if line.startswith('x '):
            args['completed'] = True
            # TODO: abstract this
            line = self.ws_re.split(line, 1)[1]

        if line.startswith('('):
            args['priority'] = 26 - (ord(line[1]) - 65)
            # TODO: abstract this
            line = self.ws_re.split(line, 1)[1]

        if self.date_re.match(line):
            date_1 = line[:10]
            # TODO: abstract this
            line = self.ws_re.split(line, 1)[1]
            if self.date_re.match(line):
                # 2 dates, first is completion, second is creation
                # TODO: parse this
                args['completed_at'] = date_1
                # TODO: parse this
                args['created_at'] = line[:10]
                # TODO: abstract this
                line = self.ws_re.split(line, 1)[1]
            else:
                # 1 date, must be creation
                # TODO: parse this
                args['created_at'] = date_1

        # The rest is description but may include tags
        args['description'] = line
        args.update(kwargs)

        return self(parse_description=True, **args)

    def __str__(self):
        out = ''
        if self.completed:
            out += 'x '
        if self.priority is not None:
            out += '('  + chr((26 - self.priority) + 65) + ') '
        if self.completed_at:
            # TODO: when parsed, format this
            out += self.completed_at + ' '
        if self.created_at:
            # TODO: when parsed, format this
            out += self.created_at + ' '
        out += self.description
        for project in self.projects:
            if '+' + project not in out:
                out += ' +' + project
        for context in self.contexts:
            if '@' + context not in out:
                out += ' @' + context
        for k, v in self.tags.items():
            if k + ':' + v not in out:
                out += ' ' + k + ':' + v

        return out


class TodoTxt(object):
    TASK_CLASS = Task

    def __init__(self, filename):
        self.filename = os.path.abspath(os.path.normpath(os.path.expanduser(filename)))
        self.tasks = []

        self.load()

    def append(self, task):
        new_id = max([t.id or 0 for t in self.tasks]) + 1
        task.id = new_id
        self.tasks.append(task)
        self.save()

    def print_tasks(self):
        for task in self.tasks:
            print task.id, str(task)

    def load(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as fp:
                for id, line in enumerate(fp):
                    line = line.strip()
                    if line:
                        self.tasks.append(self.TASK_CLASS.parse(line, id=id + 1))

    def save(self):
        with open(self.filename, 'w') as fp:
            fp.write(str(self))

    def __str__(self):
        return '\n'.join(map(str, self.tasks))


class Command(object):
    '''\
    Base command.

    The base for all other commands.
    '''

    def __init__(self, prog, config):
        self.parser = argparse.ArgumentParser(prog=prog + ' ' + self.command_name(), description=self.command_doc(), formatter_class=argparse.RawDescriptionHelpFormatter)
        self.add_parser_args()
        self.config = config
        self.todotxt = TodoTxt(config['todo.txt'])

    def add_parser_args(self):
        pass

    @classmethod
    def command_name(self):
        return self.__name__[:-7].lower()

    @classmethod
    def command_doc(self):
        return textwrap.dedent(self.__doc__)

    @classmethod
    def command_doc_oneline(self):
        return self.command_doc().split('\n')[0]

    @classmethod
    def subcommands(self, prog, config):
        out = {}
        queue = [self]
        while queue:
            cls = queue.pop()
            if cls is not self:
                out[cls.command_name()] = cls(prog, config)
            queue += cls.__subclasses__()
        return out

    def __call__(self, args):
        parsed_args = self.parser.parse_args(args)
        self.run(parsed_args)

    def run(self, args):
        raise NotImplementedError()


class ListCommand(Command):
    '''\
    List tasks.

    Print a list of tasks.
    '''

    def run(self, args):
        self.todotxt.print_tasks()


class AddCommand(Command):
    '''\
    Add a new task.
    '''

    def add_parser_args(self):
        self.parser.add_argument('description', help="Task description.  Todo.txt projects, contexts, and tags in the description will be parsed.")
        self.parser.add_argument('-C', '--complete', action='store_true', help="Mark the task as complete")
        self.parser.add_argument('-P', '--priority', help="Task priority (A-Z)")
        self.parser.add_argument('--created', help="Alternate created date (YYYY-MM-DD)")
        self.parser.add_argument('--completed', help="Completed date (YYYY-MM-DD)")
        self.parser.add_argument('-p', '--project', action='append', help="Specify a project that this task belongs to")
        self.parser.add_argument('-c', '--context', action='append', help="Specify a context that this task belongs to")
        self.parser.add_argument('-t', '--tag', nargs=2, action='append', help="Specify a key and value of a tag to add to this task", metavar=('KEY', 'VALUE'))

    def run(self, args):
        if args.priority:
            args.priority = 26 - (ord(args.priority) - 65)
        task = Task(
            args.description,
            completed=args.complete,
            priority=args.priority,
            created_at=args.created,  # TODO: now
            completed_at=args.completed,
            projects=args.project,
            contexts=args.context,
            tags=dict(args.tag) if args.tag else None,
            parse_description=True,
        )
        self.todotxt.append(task)
        self.todotxt.print_tasks()


def main():
    config = Config()
    commands = Command.subcommands(sys.argv[0], config)

    command_list = '\n'.join(['{} - {}'.format(name, c.command_doc_oneline()) for name, c in commands.items()])

    parser = argparse.ArgumentParser(description="Manage a task list", epilog="Available commands:\n" + command_list, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', help="Command to run", default='list', choices=commands.keys())
    parser.add_argument('command_args', nargs=argparse.REMAINDER, help="Arguments for the command")
    args = parser.parse_args()
    return commands[args.command](args.command_args)


if __name__ == '__main__':
    main()
    # t = TodoTxt('~/todo.txt')
    # for task in t.tasks:
    #     print task.id, str(task)