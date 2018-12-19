---
title: "Getting started with the Astronomer CLI"
link: "Getting started"
date: 2018-10-12T00:00:00.000Z
slug: "cli-getting-started"
menu: ["Astro CLI"]
position: [2]
---

If you've gotten the Astronomer CLI installed and want to get ready to start pushing DAGs, you're in the right place. Read below for some starter guidelines.

## I. Confirm the Install & Create a Project

Let's make sure you have the Astronomer CLI installed on your machine, and that you have a project to work from.

### Confirm the Install worked

Open a terminal and run:

```bash
astro
```

If you're set up properly, you should see the following:

```
astro is a command line interface for working with the Astronomer Platform.

Usage:
  astro [command]

Available Commands:
  airflow     Manage airflow projects and deployments
  auth        Mangage astronomer identity
  cluster     Manage Astronomer EE clusters
  config      Manage astro project configurations
  deployment  Manage airflow deployments
  help        Help about any command
  upgrade     Check for newer version of Astronomer CLI
  user        Manage astronomer user
  version     Astronomer CLI version
  workspace   Manage Astronomer workspaces

Flags:
  -h, --help   help for astro
```

For a breakdown of subcommands and corresponding descriptions, you can run: `astro help`

### Create a project

Your first step is to create a project to work from that lives in a folder on your local machine. The command you'll need is listed below, with an example `hello-astro` project.

 ```
mkdir hello-astro && cd hello-astro
astro airflow init
 ```

This will build a base image from Astronomer's fork of Apache-Airflow using Alpine Linux. The build process will include everything in your project directory, which makes it easy to include any shell scripts, static files, or anything else you want to include in your code.

Once that command is run, you'll see the following skeleton project generated:

```py
.
├── dags #Where your DAGs go
│   ├── example-dag.py
├── Dockerfile #For runtime overrides
├── include #For any other files you'd like to include
├── packages.txt #For OS-level packages
├── plugins #For any custom or community Airflow plugins
└── requirements.txt #For any python packages
```

**Note:** The image will take some time to build the first time. Right now, you have to rebuild the image each time you want to add an additional package or requirement.

## II. Getting Started

Now that you have a project up, we'll need to make sure you're properly authenticated to your Astronomer workspace and deployment. To do so, follow the steps below.

### Logging in from the CLI

To make sure you're authenticated, run the following:

```
astro auth login astronomer.cloud
```

**Note:** If you don't already have an account on our platform, running this command will automatically create one for you (and a default workspace as well) based on the name associated with your Google email address).

If do already have an account on our app (app.astronomer.cloud), then press enter when you see something like:

```
 "Paolas-MBP-2:hello-astro paola$ astro auth login astronomer.cloud
 CLUSTER                             WORKSPACE                           
 astronomer.cloud                    4a6cb370-c361-440d-b02b-c90b07ef15f6

 Switched cluster
Username (leave blank for oAuth): 
```

Once you press enter, you’ll be prompted to go back into our UI to this link: https://app.astronomer.cloud/token

Grab that token, paste it back into your command line, and you’re good to go. Your success message should read:

```
Successfully authenticated to registry.astronomer.cloud
```

### Navigating Workspaces

Once logged in, you'll want to know how to navigate your existing workspaces. To pull a list of workspaces you're a part of, run:

```
astro workspace list
```

You should see a list of 1 or more workspaces in the output. To “pick” one, run our switch command followed by the corresponding ID (no syntax needed around the ID):

```
astro workspace switch <workspace UUID>
```

### Navigating Deployments

If you haven't created a deployment via the UI (recommended), you _can_ do so via the Astronomer CLI.

#### Creating a deployment via the Astronomer CLI

To create a deployment directly from our CLI, run:

`astro deployment create <deployment name>`

**Note:** This is a bit misleading. `deployment name` here is your workspace ID (that you pulled above), NOT the name of your new deployment (which doesn’t exist yet).

Once your webserver, scheduler, and celery flower are up, you should see the following success message and URLs:

```
Successfully created deployment. Deployment can be accessed at the following URLs 

 Airflow Dashboard: https://popular-orbit-2745-airflow.astronomer.cloud
 Flower Dashboard: https://popular-orbit-2745-flower.astronomer.cloud
```

#### Listing your Deployments

To pull a list of deployments you're authorized to push to, run:

```
astro deployment list
```

To “pick” a deployment to push up a DAG to (a bit different than picking a workspace), just run:

```
astro airflow deploy
```

This command will return a list of deployments available in that workspace, and prompt you to pick one.

```
 #    RELEASE NAME                  WORKSPACE                     DEPLOYMENT UUID                                   
 1    false-wavelength-5456         Paola Peraza Calderon's Workspace90b3dc76-2022-4e0f-9bac-74a03d0dffa7
 ````

## III. CLI Debugging

### Error on Building Image

If your image  is failing to build after running `astro airflow start`?

 - You might be getting an error message in your console, or finding that Airflow is not accessible on `localhost:8080/admin`
 - If so, you're likely missing OS-level packages in `packages.txt` that are needed for any python packages specified in `requirements.text`

### Adding Packages & Requirements

If you're not sure what `packages` and `requirements` you need for your use case, check out these examples:

 - [Snowflake](https://github.com/astronomer/airflow-guides/tree/master/example_code/snowflake)
 - [Google Cloud](https://github.com/astronomer/airflow-guides/tree/master/example_code/gcp)

If image size isn't a concern, feel free to "throw the kitchen sink at it" with this list of packages:

```
libc-dev
musl
libc6-compat
gcc
python3-dev
build-base
gfortran
freetype-dev
libpng-dev
openblas-dev
gfortran
build-base
g++
make
musl-dev
```

**Note**: By default, there won't be webserver or scheduler logs in the terminal since everything is hidden away in Docker containers.

You can see these logs by running: 

```
docker logs $(docker ps | grep scheduler | awk '{print $1}')
```

## IV. CLI Help Commands

The CLI includes a help command, descriptions, as well as usage info for subcommands.

To see the help overview:

```
astro help
```

Or for subcommands:

```
astro airflow --help
```

```
astro airflow deploy --help
```

## V. Using Airflow CLI Commands

You can still use all native Airflow CLI commands with the astro cli when developing DAGs locally -  they'll just need to be wrapped around docker commands.

Run `docker ps` after your image has been built to see a list of containers running. You should see one for the scheduler, webserver, and Postgres.

For example, a connection can be added with:

```bash
docker exec -it SCHEDULER_CONTAINER bash -c "airflow connections -a --conn_id test_three  --conn_type ' ' --conn_login etl --conn_password pw --conn_extra {"account":"blah"}"
```

Refer to the native [Airflow CLI](https://airflow.apache.org/cli.html) for a list of all commands.

**Note**: This will only work for the local dev environment.

## VI. Overriding Environment Variables

Astronomer v0.7 comes with the ability to inject Environment Variables directly through the UI.

With that said, you can also throw any overrides in the `Dockerfile` if you want to make sure those variables get version controlled. To do so, follow these guidlines:

 - Any bash scripts you want to run as `sudo` when the image builds can be added as such:
`RUN COMMAND_HERE`
 - Airflow configuration variables can be found in [`airflow.cfg`](https://github.com/apache/incubator-airflow/blob/master/airflow/config_templates/default_airflow.cfg) can be overwritten with the following format:

```
 ENV AIRFLOW__SECTION__PARAMETER VALUE
```
For example, setting `max_active_runs` to 3 would look like:

```
AIRFLOW__CORE__MAX_ACTIVE_RUNS 3
```

These commands should go after the `FROM` line that pulls down the Airflow image.

**Note:** Be sure your configuration names match up with the version of Airflow you're using.
