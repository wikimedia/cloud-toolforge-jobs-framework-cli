# toolforge jobs framework -- command line interface

This is the source code of command line interface part of the Toolforge Jobs Framework.

## Usage

Some usage examples.

Show help:

```console
$ toolforge-jobs --help
usage: toolforge-jobs.py [-h] [--debug] [--kubeconfig KUBECONFIG] [--url URL] [--hdr HDR] {containers,run,show,list,delete,flush} ...

Toolforge Jobs Framework, command line interface

positional arguments:
  {containers,run,show,list,delete,flush}
                        possible operations (pass -h to know usage of each)
    containers          list information on available container types for Toolforge jobs
    run                 run a new job of your own in Toolforge
    show                show details of a job of your own in Toolforge
    list                list all running jobs of your own in Toolforge
    delete              delete a running job of your own in Toolforge
    flush               delete all running jobs of your own in Toolforge

optional arguments:
  -h, --help            show this help message and exit
  --debug               activate debug mode
  --kubeconfig KUBECONFIG
                        user kubeconfig file. Defaults to '~/.kube/config'
  --url URL             use custom URL for the Toolforge jobs framework API endpoint
  --hdr HDR             use custom HTTP headers to contact the Toolforge jobs framework API endpoint

```

Get containers list:

```console
$ toolforge-jobs containers
Short name     Docker container image
-------------  --------------------------------------------------------------------
tf-buster      docker-registry.tools.wmflabs.org/toolforge-buster-sssd:latest
tf-buster-std  docker-registry.tools.wmflabs.org/toolforge-buster-standalone:latest
```

Run a job:

```console
$ toolforge-jobs run myjob --command ./sleep.sh --image tf-buster-std
$ toolforge-jobs list
Job id    Job command    image shortname    Job status    Job type
--------  -------------  -----------------  ------------  ----------
myjob     ./sleep.sh     tf-buster-std      unknown       normal
```

## Installation

TODO

## Contributing

TODO

## License
[GPLv3](https://choosealicense.com/licenses/gpl-3.0/)
