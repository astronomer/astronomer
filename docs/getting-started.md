---
title: "Getting started with Astronomer"
date: 2018-10-12T00:00:00.000Z
slug: "getting-started"
menu: ["root"]
position: [2]
---

## Sign up

First step, [create an account](https://app.astronomer.cloud/).

If you're new to Astronomer but someone else on your team has an existing workspace you want to join, you still have to create your own account. Once you're signed up, they can invite you to their workspace.

## Download the CLI

To use the CLI, you'll need the following installed on your machine:

- [Docker](https://www.docker.com/get-started)
- [Go](https://golang.org/)

Run the following command:

```
curl -sSL https://install.astronomer.io | sudo bash
```

If you need to install an older version of our CLI:

```
curl -sSL https://install.astronomer.io | sudo bash -s -- [TAGNAME]
```

### Confirm CLI Install

To confirm the install worked:

```bash
astro
```

Then create a project:

```bash
mkdir hello-astro && cd hello-astro
astro airflow init
```

### For WSL (Windows Subsystem for Linux) Users

- If you're running WSL, you might see the following error when trying to call `astro airflow start` on your newly created workspace.

```
Sending build context to Docker daemon  8.192kB
Step 1/1 : FROM astronomerinc/ap-airflow:latest-onbuild
# Executing 5 build triggers
 ---> Using cache
 ---> Using cache
 ---> Using cache
 ---> Using cache
 ---> Using cache
 ---> f28abf18b331
Successfully built f28abf18b331
Successfully tagged hello-astro/airflow:latest
INFO[0000] [0/3] [postgres]: Starting
Pulling postgres (postgres:10.1-alpine)...
panic: runtime error: index out of range
goroutine 52 [running]:
github.com/astronomer/astro-cli/vendor/github.com/Nvveen/Gotty.readTermInfo(0xc4202e0760, 0x1e, 0x0, 0x0, 0x0)
....
```

This is an issue pulling Postgres. To fix it, you should be able to run the following:

```
Docker pull postgres:10.1-alpine
```

## Get started with the new CLI

For a breakdown of subcommands and corresponding descriptions, you can run: `astro help`

When you're ready, run the following in a project directory: `astro airflow init`

This will generate some skeleton files:

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

For more specific guidance on working with our CLI, go [here](https://astronomer.io/docs/cli-getting-started).

## Customizing your image

Our base image runs Alpine Linux, so it is very slim by default.

- Add DAGs in the `dags` directory,
- Add custom airflow plugins in the `plugins` directory
- Python packages can go in `requirements.txt`. By default, you get all the python packages required to run airflow.
- OS level packages  can go in `packages.txt`
- Any envrionment variable overrides can go in `Dockerfile`

If you are unfamiliar with Alpine Linux, look here for some examples of what
you will need to add based on your use-case:

- [GCP](https://github.com/astronomer/airflow-guides/tree/master/example_code/gcp/example_code)
- [Snowflake](https://github.com/astronomer/airflow-guides/tree/master/example_code/snowflake/example_code)
- More coming soon!

## Run Apache Airflow Locally

Once you've added everything you need, run: `astro airflow start`

This will spin up a local Airflow for you to develop on that includes locally running docker containers - one for the Airflow Scheduler, one for the Webserver, and one for postgres (Airflow's underlying database).

To verify that you're set, you can run: `docker ps`

## Migrate your DAGs

If you're a previous user of Astronomer Cloud or have a pre-existing Airflow instance, migrating your DAGs should be straightforward.

## Tips

Astronomer Cloud runs Python 3.6.6. If you're running a different version, don't sweat it. Our CLI spins up a containerized environment, so you don't need to change anything on your machine if you don't want to.

For the sake of not over-exposing data and credentials, there's no current functionality that allows you to automatically port over connections and variables from a prior Apache Airflow instance. You'll have to do this manually as you complete the migration.

The Airflow UI doesn't always show the full stacktrace. To get some more information while you're developing locally, you can run:

```bash
docker logs $(docker ps | grep scheduler | awk '{print $1}')
```
Before you deploy a new DAG, verify that everything runs as expected locally.

As you add DAGs to your new project's `dags` directory, check the UI for any error messages that come up.

## DAG Deployment

Once you can get your DAGs working locally, you are ready to deploy them.

### Step 1: CLI Login + Auth

To log in and pass our authorization flow via the CLI, you'll have to run the following command:

```
astro auth login astronomer.cloud
```

If you don't already have an account on our platform, running this command will automatically create one for you (and a default workspace as well) based on the name associated with your Google email address.

You _can_ login via app.cloud.astronomer directly but our UI currently does not display the workspace ID you'll need to complete a deployment.

### Step 2: Pull your list of workspaces

In order to deploy, you'll first need to verify your default workspace by pulling a list of all workspaces associated with your account.

To do so, run:

  `astro workspace list`

### Step 3: Create a new deployment

  If you're a new user, you can create a new deployment by running:

  `astro deployment create <deployment name>`

### Step 4: View Deployments

  Once you've run your first deploy and you've made sure you're in the right workspace, all you'll have to do moving forward is list your active deployments by running:

  `astro deployment list`

  This commnand will return a list of Airflow instances you're authorized to deploy to.

### Step 5: Deploy

When you're ready to deploy, run:

  `astro airflow deploy`

This command will return a list of deployments available in that workspace, and prompt you to pick one.

## Frequently Asked Questions

Check out our [web forum](https://forum.astronomer.io) for FAQs and community discussion.
