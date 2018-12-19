---
title: "Getting started with Astronomer"
date: 2018-10-12T00:00:00.000Z
slug: "getting-started"
menu: ["root"]
position: [2]
---

Welcome to Astronomer Cloud Edition. 

Whether you're here because you're our newest customer, or because you're wondering what working with Astronomer would look like for your team, we're excited to be with you on your Airflow journey.

To help you hit the ground running, this guide will walk you through what you need to know (and do) to get started with Astro Cloud.

## Create a Workspace

Your first step is to [start a trial here](https://trial.astronomer.io).

From there, you'll be redirected to our app to create an account and workspace.

**Note:** If you're new to Astronomer but someone else on your team has an existing workspace you want to join, you'll still need to sign up. A personal workspace for you will be generated regardless, but they'll be able to add you as a user to a shared workspace directly from their account.

## Develop with the Astronomer CLI

### Install

Once you have a workspace, your next step is to get set up with our CLI and start developing locally.

Follow our [CLI Install guide](https://www.astronomer.io/docs/cli-installation/) to get set up.

### Get Started

Once installed, head over to our [CLI Getting Started Guide](https://astronomer.io/docs/cli-getting-started) for guidelines on how to create your first project, navigate both your workspace and deployments, and debug errors if needed.

## Build your Image

Once you've created a project, made sure you're in the right place and feel comfortable with our CLI commands, run the following in a project directory: `astro airflow init`

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

## Customize your image

Our base image runs Alpine Linux, so it is very slim by default.

- Add DAGs in the `dags` directory
- Add custom airflow plugins in the `plugins` directory
- Python packages can go in `requirements.txt`. By default, you get all the python packages required to run airflow.
- OS level packages  can go in `packages.txt`
- Any envrionment variable overrides can go in `Dockerfile` (_note_: with Astronomer 0.7, you can also inject env vars directly through the UI)

As you add DAGs to your new project's `dags` directory, check the Airflow UI for any error messages that come up.

If you are unfamiliar with Alpine Linux, look here for some examples of what
you will need to add based on your use-case:

- [GCP](https://github.com/astronomer/airflow-guides/tree/master/example_code/gcp/example_code)
- [Snowflake](https://github.com/astronomer/airflow-guides/tree/master/example_code/snowflake/example_code)
- More coming soon!

## Run Apache Airflow Locally

Before you're ready to deploy your DAGs, you'll want to make sure that everything runs locally as expected.

If you've made sure everything you need to your image is set, you can run:

```bash
astro airflow start
```

This will spin up a local Airflow for you to develop on that includes locally running docker containers - one for the Airflow Scheduler, one for the Webserver, and one for postgres (Airflow's underlying database).

To verify, you can run: `docker ps`

The Airflow UI doesn't always show the full stacktrace. To get some more information while you're developing locally, you can run:

```bash
docker logs $(docker ps | grep scheduler | awk '{print $1}')
```

### Note on Python Versioning

Astronomer Cloud runs Python 3.6.6. If you're running a different version, don't sweat it. Our CLI spins up a containerized environment, so you don't need to change anything on your machine if you don't want to.

## Create an Airflow Deployment

If you already have a deployment up, you can skip this step. If not, go ahead and create a deployment directly from our app by following the steps below:

- Start from https://app.astronomer.cloud/workspaces
- Click into the workspace you want to create a deployment from
- Hit `New Deployment` on the top right of the page
- Give your deployment a name and description
- Wait a few minutes (might have to refresh) for your webserver, scheduler, and celery flower (worker monitoring) to spin up

Once you see an active URL under “Apache Airflow” in the middle of the page, you are set and ready to deploy your DAGs.

**Note**: For abstraction from the Astro UI, you can also create a deployment [via the CLI](https://www.astronomer.io/docs/cli-getting-started/).

## Migrate your DAGs

If you're a previous user of Astronomer Cloud or have a pre-existing Airflow instance, migrating your DAGs should be straightforward.

For the sake of not over-exposing data and credentials, there's no current functionality that allows you to automatically port over connections and variables from a prior Apache Airflow instance. You'll have to do this manually as you complete the migration.

## DAG Deployment

Once your DAGs are working locally, you're ready for deployment.

### Step 1: Login

To log in to your existing account and pass our authorization flow, run the following command:

```
astro auth login astronomer.cloud
```

You _can_ login via app.cloud.astronomer directly but our UI currently does not display the workspace ID you'll need to complete a deployment.

### Step 2: Make sure you're in the right place

To get ready for deployment, make sure:

- You're logged in, per above
- You're in the right workspace
- Your target deployment lives under that workspace

Follow our [CLI Getting Started Guide](https://www.astronomer.io/docs/cli-getting-started/) for more specific guidelines and commands.

### Step 3. Deploy

When you're ready to deploy your DAGs, run:

  `astro airflow deploy`

This command will return a list of deployments available in that workspace, and prompt you to pick one.

## Frequently Asked Questions

Check out our [web forum](https://forum.astronomer.io) for FAQs and community discussion.
