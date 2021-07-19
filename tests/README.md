# DISCLAIMER

The author doesn't know yet (didn't invest time) into doing this in a more pythonic way. The goal
was to just have a way to run a bunch of commands and check the output.

We can create a proper pytest testsuite later once we have time for it.

Even better: we can work on triggering these tests from our jekins CI pipeline.
There are several complexities in doing that, such as setting the environment: remember, we need a
Kubernetes API, directories, etc.

# How to use it

The `cmd-checklist.yaml` file should be equivalent of manually running a bunch of commands.

There must be a reachable jobs-api API endpoint somewhere. If running this locally, you likely
need to refer to cloud/toolforge/jobs-framework-api.git devel/README.md.

Then:

```
$ tests/cmd-checklist-runner.py --config-file tests/cmd-checklist.yaml
```

The testsuite assumes the FQDN being tested is 'jobs.svc.toolsbeta.eqiad1.wikimedia.cloud', which
is listening in https:localhost:30001. This can be overriden by passing env vars to the runner
script (see YAML for var names).

```
$ CUSTOMADDR="127.0.0.1" CUSTOMFQDN="jobs.svc.toolsbeta.eqiad1.wikimedia.cloud" CUSTOMURL="https://localhost:30001/api/v1" tests/cmd-checklist-runner.py --config-file tests/cmd-checklist.yaml
```


