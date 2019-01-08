---
title: "DAG Deployment"
description: "How to deploy your DAGs to your Astronomer Enterprise cluster using the Astronomer CLI."
date: 2018-10-12T00:00:00.000Z
slug: "ee-dag-deployment"
menu: ["Enterprise Edition"]
position: [3]
---

# Deploying to Astronomer Enterprise

Once you've finished up the installation, you are ready to deploy DAGs. We'll walk through deploying  Airflow DAG via the [astro-cli](https://github.com/astronomer/astro-cli), but you can also check out our CI/CD guide for deploying through another system.

We'll walk through deploying a sample DAG to make sure your installation works as expected.

(**Note:** If you're looking for steps on how to deploy to your Astronomer Cloud account, check out our [Getting Started with Cloud](https://www.astronomer.io/guides/getting-started-with-new-cloud/) guide).

### 1. Initialize and Authenticate

Run:
```bash
astro airflow init
```

This will generate a project structure, as well as a sample DAG and plugin. You can read more about how our CLI works [here](https://github.com/astronomer/astro-cli).

You can run

```bash
astro airflow start
```
to spin up a local Airflow environment.

Finally, authenticate with:

```bash
astro auth login [baseDomain]
```

*Note:* Depending on the type of authentication you're using, the process will be a little different. If you are using the default Google OAuth, leave the Username field blank and continue follow the instructions on the terminal.

### 2. Configure and spin up a deployment

Once you've authenticated, head over to `app.BASEDOMAIN` and spin up and configure a new deployment.

![Deployment Page](https://assets2.astronomer.io/guides/docs/ee/deployment_page.png)

Click `New Deployment`

![Configure Deployment](https://assets2.astronomer.io/guides/docs/ee/configure_deployment.png)

You'll be able to further configure your deployment after your initialize it. Wait a few minutes and it should be ready!

![Deployment Ready](https://assets2.astronomer.io/guides/docs/ee/deployment_ready.png)

### 3. List your workspaces

Run `astro workspace list` from the CLI to see a list of all the workspaces you have access to.

To switch between workspaces, run: `astro workspace switch [UUID]`

### 4. Run our deploy command

```bash
astro airflow deploy [release-name]
```

If you do NOT include a release name, you will be prompted to choose from a deployment in the workspace you are pointing to.

After deploying, you'll see some stdout as the CLI builds and pushes images to your private registry.

### 5. Check your Instance

Once you push your code, jump over to your deployment and you'll see the code you had locally running in your Astronomer environment!
