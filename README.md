# toolforge jobs framework -- command line interface

This is the source code of command line interface part of the Toolforge Jobs Framework.

The TJF creates an abstraction layer over kubernetes Jobs, CronJobs and Deployments to allow
operating a Kubernetes installation as if it were a Grid (like GridEngine).

This was created for [Wikimedia Toolforge](https://toolforge.org).

## Usage

The help message:

```console
$ toolforge-jobs --help
usage: toolforge-jobs [-h] [--debug] [--cfg CFG] {containers,run,show,list,delete,flush,load} ...

Toolforge Jobs Framework, command line interface

positional arguments:
  {containers,run,show,list,delete,flush,load}
                        possible operations (pass -h to know usage of each)
    containers          list information on available container types for Toolforge jobs
    run                 run a new job of your own in Toolforge
    show                show details of a job of your own in Toolforge
    list                list all running jobs of your own in Toolforge
    delete              delete a running job of your own in Toolforge
    flush               delete all running jobs of your own in Toolforge
    load                flush all jobs and load a YAML file with job definitions and run them

optional arguments:
  -h, --help            show this help message and exit
  --debug               activate debug mode
  --cfg CFG             YAML config for the CLI. Defaults to '/etc/toolforge-jobs-framework-cli.cfg'. Only useful for Toolforge admins.
```

More information at [Wikitech](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Jobs_framework) and in the man page.

## Installation

We currently deploy this code into Toolforge using a debian package that is built from this very
source tree.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[GPLv3](https://choosealicense.com/licenses/gpl-3.0/)
