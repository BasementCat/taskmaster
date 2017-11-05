#! /usr/bin/env python

import sys
import os
import re
import argparse
import textwrap
import copy
from collections import OrderedDict

import pendulum
from dateutil import rrule


pendulum.set_formatter('alternative')


def iso8601dt(dt):
    if not isinstance(dt, pendulum.pendulum.Pendulum):
        dt = pendulum.parse(dt)
    return dt.in_timezone('UTC').format('YYYY-MM-DD[T]HH:mm:ss[Z]')


def parse_date(dt):
    if not isinstance(dt, pendulum.pendulum.Pendulum):
        dt = pendulum.parse(dt)
    return dt.in_timezone('UTC').hour_(0).minute_(0).second_(0).microsecond_(0)


def format_date(dt):
    return dt.format('YYYY-MM-DD')


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


class TaskListMixin(object):
    TASK_LIST_ATTR = 'tasks'

    @property
    def _tasklist(self):
        if not hasattr(self, self.TASK_LIST_ATTR):
            setattr(self, self.TASK_LIST_ATTR, [])
        return getattr(self, self.TASK_LIST_ATTR)

    def append(self, task):
        if self._tasklist:
            new_id = max([t.id or 0 for t in self._tasklist]) + 1
        else:
            new_id = 1
        task.id = new_id
        self._tasklist.append(task)

    def print_tasks(self):
        for task in self._tasklist:
            print task.id, str(task)

    def get(self, id):
        try:
            ids = map(lambda v: int(v) - 1, str(id).split('.'))
            task = self._tasklist[ids.pop(0)]
            while ids:
                task = task._tasklist[ids.pop(0)]
            return task
        except IndexError:
            return None


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
            self.parse_description()

    def parse_description(self):
        new_description = []

        for candidate in split_with_ws(self.description):
            if candidate.startswith('+') and len(candidate.strip()) > 1:
                self.projects.append(candidate[1:].strip())
            elif candidate.startswith('@') and len(candidate.strip()) > 1:
                self.contexts.append(candidate[1:].strip())
            elif ':' in candidate and len(candidate.strip()) > 2:
                k, v = candidate.strip().split(':', 1)
                self.tags[k] = v
            else:
                new_description.append(candidate)

        self.description = ''.join(new_description).strip()

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
                args['completed_at'] = parse_date(date_1)
                args['created_at'] = parse_date(line[:10])
                # TODO: abstract this
                line = self.ws_re.split(line, 1)[1]
            else:
                # 1 date, must be creation
                args['created_at'] = parse_date(date_1)

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
            out += format_date(self.completed_at) + ' '
        if self.created_at:
            out += format_date(self.created_at) + ' '
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

    def clone(self):
        return self.__class__(
            self.description,
            completed=self.completed,
            priority=self.priority,
            created_at=self.created_at,
            completed_at=self.completed_at,
            projects=self.projects,
            contexts=self.contexts,
            tags=self.tags,
        )


class TodoTxt(TaskListMixin):
    TASK_CLASS = Task

    def __init__(self, filename):
        self.filename = os.path.abspath(os.path.normpath(os.path.expanduser(filename)))
        self.tasks = []

        self.load()

    def load(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as fp:
                id = 1
                for line in fp:
                    line = line.strip()
                    if line:
                        self.tasks.append(self.TASK_CLASS.parse(line, id=id))
                        id += 1

    def save(self):
        with open(self.filename, 'w') as fp:
            fp.write(str(self))

    def __str__(self):
        return '\n'.join(map(str, self.tasks))


class TMTask(TaskListMixin, Task):
    TASK_LIST_ATTR = 'subtasks'

    def _parse_rrule(self, value):
        rset = rrule.rruleset()
        for candidate in value.split(';;'):
            if candidate.startswith('RRULE:'):
                rset.rrule(rrule.rrulestr(candidate.replace(';', '\n'), dtstart=self.due or pendulum.utcnow()))
            elif candidate.startswith('EXRULE:'):
                rset.exrule(rrule.rrulestr('RRULE:' + candidate[7:].replace(';', '\n'), dtstart=self.due or pendulum.utcnow()))
            elif candidate.startswith('RDATE:'):
                rset.rdate(pendulum.parse(candidate[6:]))
            elif candidate.startswith('EXDATE:'):
                rset.exdate(pendulum.parse(candidate[7:]))
        return rset

    def _str_rruleset(self, value):
        out = []
        values = [
            ('RRULE', value._rrule),
            ('RDATE', value._rdate),
            ('EXRULE', value._exrule),
            ('EXDATE', value._exdate),
        ]
        for prefix, data in values:
            for v in data:
                out.append(prefix + ':' + str(v).replace('\n', ';'))
        return ';;'.join(out)

    def __init__(self, *args, **kwargs):
        self.TAG_PARSERS = OrderedDict([
            ('due', (parse_date, format_date)),
            ('rrule', (self._parse_rrule, self._str_rruleset)),
        ])
        self.subtasks = kwargs.pop('subtasks', [])
        depth = kwargs.pop('depth', 0)
        parse_description = kwargs.pop('parse_description', False)
        super(TMTask, self).__init__(*args, **kwargs)
        if parse_description:
            self.parse_description(depth=depth)
        self.parse_tags()

    def parse_description(self, depth=0):
        new_description = []
        found_subtasks = False
        subtask_id = 1
        candidates = re.split(ur'(\s+' + ('&&' * (depth + 1)) + '[^&])', self.description)
        while candidates:
            candidate = candidates.pop(0)
            if candidate.strip().startswith('&&' * (depth + 1)):
                found_subtasks = True
                candidate = (candidate + candidates.pop(0)).strip().lstrip('&')
                self.subtasks.append(TMTask.parse(candidate, depth=depth + 1, id=subtask_id))
                subtask_id += 1
            elif not found_subtasks:
                new_description.append(candidate)

        self.description = ''.join(new_description)
        super(TMTask, self).parse_description()

    def parse_tags(self):
        for tag, (parser, _) in self.TAG_PARSERS.items():
            setattr(self, tag, None)
            if self.tags.get(tag):
                setattr(self, tag, parser(self.tags[tag]))

    def _make_string(self, depth=0, include_subtasks=True):
        for tag, (_, stringifier) in self.TAG_PARSERS.items():
            if getattr(self, tag) is None:
                if tag in self.tags:
                    del self.tags[tag]
            else:
                self.tags[tag] = stringifier(getattr(self, tag))

        out = super(TMTask, self).__str__()
        if include_subtasks:
            if depth > 0:
                out = ' ' + ('&&' * depth) + out
            out += ''.join([t._make_string(depth=depth + 1) for t in self.subtasks])
        return out

    def __str__(self):
        return self._make_string()

    def clone(self):
        out = super(TMTask, self).clone()
        out.parse_tags()
        return out


class TMTodoTxt(TodoTxt):
    TASK_CLASS = TMTask

    @classmethod
    def _print_task_list(self, tasks, depth=0, parent_id=None):
        for task in tasks:
            prefix = ''
            if depth > 0:
                prefix = ('  ' * depth) + str(parent_id) + '.'
            print prefix + str(task.id), task._make_string(include_subtasks=False)
            self._print_task_list(task.subtasks, depth=depth + 1, parent_id=(parent_id + '.' if parent_id else '') + str(task.id))

    def print_tasks(self):
        self._print_task_list(self.tasks)


class CommandError(Exception):
    pass


class Command(object):
    '''\
    Base command.

    The base for all other commands.
    '''

    def __init__(self, prog, config):
        names = self.command_names()
        if len(names) > 1:
            names = '{{{}}}'.format(','.join(names))
        else:
            names = names[0]
        self.parser = argparse.ArgumentParser(prog=prog + ' ' + names, description=self.command_doc(), formatter_class=argparse.RawDescriptionHelpFormatter)
        self.add_parser_args()
        self.config = config
        self.todotxt = TMTodoTxt(config['todo.txt'])

    def add_parser_args(self):
        pass

    @classmethod
    def command_names(self):
        return [self.__name__[:-7].lower()]

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
                names = list(filter(lambda v: not v.startswith('_'), cls.command_names()))
                if names:
                    instance = cls(prog, config)
                    for name in names:
                        out[name] = instance
            queue += cls.__subclasses__()
        return out

    def __call__(self, args):
        parsed_args = self.parser.parse_args(args)
        try:
            return self.run(parsed_args) or 0
        except CommandError as e:
            sys.stderr.write(str(e) + '\n')
            return 1

    def run(self, args):
        raise NotImplementedError()


class _WrappedCommand(object):
    def __init__(self, *args, **kwargs):
        self.run = self.run_wrapper(self.run)
        super(_WrappedCommand, self).__init__(*args, **kwargs)


class _SingleTaskCommand(_WrappedCommand):
    def add_parser_args(self):
        self.parser.add_argument('task_id', help="Task ID (1, 2.4, etc)")
        super(_SingleTaskCommand, self).add_parser_args()

    def run_wrapper(self, run):
        def wrapped(args):
            task = self.todotxt.get(args.task_id)
            if not task:
                raise CommandError("No such task")
            args.task = task
            return run(args)
        return wrapped


def _EditingCommand(desc_as_flag=False, with_subtask=True):
    class _EditingCommandImpl(object):
        def add_parser_args(self):
            if desc_as_flag:
                self.parser.add_argument('-d', '--description', help="Task description.  Todo.txt projects, contexts, and tags in the description will be parsed.")
            else:
                self.parser.add_argument('description', help="Task description.  Todo.txt projects, contexts, and tags in the description will be parsed.")
            self.parser.add_argument('-C', '--complete', action='store_true', help="Mark the task as complete")
            self.parser.add_argument('-P', '--priority', help="Task priority (A-Z)", type=lambda v: 26 - (ord(v) - 65))
            self.parser.add_argument('--created', help="Alternate created date (YYYY-MM-DD)", type=parse_date)
            self.parser.add_argument('--completed', help="Completed date (YYYY-MM-DD)", type=parse_date)
            self.parser.add_argument('-p', '--project', action='append', help="Specify a project that this task belongs to")
            self.parser.add_argument('-c', '--context', action='append', help="Specify a context that this task belongs to")
            self.parser.add_argument('-t', '--tag', nargs=2, action='append', help="Specify a key and value of a tag to add to this task", metavar=('KEY', 'VALUE'))
            if with_subtask:
                self.parser.add_argument('-s', '--subtask-of', help="Create this task as a subtask of another task")
            self.parser.add_argument('--due', help="Due date (YYYY-MM-DD)", type=parse_date)
            super(_EditingCommandImpl, self).add_parser_args()
    return _EditingCommandImpl


class ListCommand(Command):
    '''\
    List tasks.

    Print a list of tasks.
    '''

    def run(self, args):
        self.todotxt.print_tasks()


class ShowCommand(_SingleTaskCommand, Command):
    '''\
    Show a task.

    Show a single task.
    '''

    @classmethod
    def command_names(self):
        return ['show', 's']

    def run(self, args):
        print args.task.id, args.task._make_string(include_subtasks=False)


class NextCommand(_SingleTaskCommand, Command):
    '''\
    Add the next instance of a recurring task.

    Clone the given task, and add it to the task list (uncompleted) with its due date set to the next recurring date.
    '''

    def run(self, args):
        if not args.task.rrule:
            raise CommandError("The task does not recur")
        new_task = args.task.clone()
        new_task.completed = False
        if new_task.rrule:
            new_task.due = new_task.rrule.after(new_task.due or pendulum.utcnow())
        for rule in new_task.rrule._rrule + new_task.rrule._exrule:
            rule._dtstart = new_task.due
        self.todotxt.append(new_task)
        self.todotxt.print_tasks()
        self.todotxt.save()


class AddCommand(_EditingCommand(), Command):
    '''\
    Add a new task.
    '''

    @classmethod
    def command_names(self):
        return ['add', 'a']

    def run(self, args):
        task = TMTask(
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
        if args.due:
            task.due = args.due
        if args.subtask_of:
            self.todotxt.get(args.subtask_of).append(task)
        else:
            self.todotxt.append(task)
        self.todotxt.print_tasks()
        self.todotxt.save()

class EditCommand(_SingleTaskCommand, _EditingCommand(desc_as_flag=True, with_subtask=False), Command):
    '''\
    Edit a task.
    '''

    @classmethod
    def command_names(self):
        return ['edit', 'e']

    def run(self, args):
        args.task.description = args.description or args.task.description
        args.task.completed = args.complete or args.task.completed
        args.task.priority = args.priority or args.task.priority
        args.task.created_at = args.created or args.task.created_at
        args.task.completed_at = args.completed or args.task.completed_at

        # TODO: remove projects
        if args.project:
            for project in args.project:
                args.task.projects.append(project)
        # TODO: remove contexts
        if args.context:
            for context in args.context:
                args.task.contexts.append(context)
        # TODO: remove tags
        if args.tag:
            for key, value in args.tag:
                args.task.tags[key] = value

        if args.due:
            args.task.due = args.due

        print args.task._make_string(include_subtasks=False)
        self.todotxt.save()


def main():
    config = Config()
    commands = Command.subcommands(sys.argv[0], config)

    command_name_groups = {}
    for name, c in commands.items():
        command_name_groups.setdefault(c, []).append(name)
    command_list = '\n'.join(['{} - {}'.format(', '.join(names), c.command_doc_oneline()) for c, names in command_name_groups.items()])

    parser = argparse.ArgumentParser(description="Manage a task list", epilog="Available commands:\n" + command_list, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', help="Command to run", default='list', choices=commands.keys())
    parser.add_argument('command_args', nargs=argparse.REMAINDER, help="Arguments for the command")
    args = parser.parse_args()
    return commands[args.command](args.command_args)


if __name__ == '__main__':
    sys.exit(main() or 0)
