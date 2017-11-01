# taskmaster

A set of tools to manage projects and tasks using the todo.txt standard - http://todotxt.org/


## Differences From the Standard

  * Projects, contexts, and tags are removed from the description, and appended to it when written back out to the file

## Extensions

### Subtasks

Subtasks may be added to a task.  To preserve compatibility with the todo.txt standard, these subtasks are appended to the end of a task.  A subtask starts with one or more whitespace characters, and two ampersands (&amp;):

    Sample Task &&Sample Subtask

Subtasks may be nested by using two additional ampersands to the previous level, like so:

    Top level task &&First level subtask &&&&Second level subtask &&&&&&Third level subtask

Additional lower level subtasks may follow:

    Top level task &&first level subtask &&&&second level subtask &&another first level subtask

To avoid breaking parsing, task descriptions may not include " &&" (improvements to the parser that would fix this or an alternative standard maintaining the sortability of a todo.txt file are welcome)