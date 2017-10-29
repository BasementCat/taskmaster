#! /usr/bin/env python

import os
import re
import argparse
import textwrap
import sys


class Task(object):
    ws_re = re.compile(ur'\s+')
    date_re = re.compile(ur'^\d{4}-\d{2}-\d{2}')

    def __init__(self, description, completed=False, priority=None, created_at=None, completed_at=None, projects=None, contexts=None, tags=None, id=None):
        self.description = description
        self.completed = completed
        self.priority = priority
        self.created_at = created_at
        self.completed_at = completed_at
        self.projects = projects or []
        self.contexts = contexts or []
        self.tags = tags or {}
        self.id = id

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
        for candidate in self.ws_re.split(line):
            if candidate.startswith('+'):
                args['projects'].append(candidate[1:])
            elif candidate.startswith('@'):
                args['contexts'].append(candidate[1:])
            elif ':' in candidate:
                k, v = candidate.split(':', 1)
                args['tags'][k] = v

        args.update(kwargs)

        return self(**args)

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

    def __init__(self, prog):
        self.parser = argparse.ArgumentParser(prog=prog + ' ' + self.command_name(), description=self.command_doc(), formatter_class=argparse.RawDescriptionHelpFormatter)

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
    def subcommands(self, prog):
        out = {}
        queue = [self]
        while queue:
            cls = queue.pop()
            if cls is not self:
                out[cls.command_name()] = cls(prog)
            queue += cls.__subclasses__()
        return out

    def __call__(self, args):
        parsed_args = self.parser.parse_args(args)
        self.run(args)

    def run(self, args):
        raise NotImplementedError()


class ListCommand(Command):
    '''\
    List tasks.

    Print a list of tasks.
    '''

    def run(self, args):
        for task in TodoTxt('~/todo.txt').tasks:
            print task.id, str(task)


def main():
    commands = Command.subcommands(sys.argv[0])

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