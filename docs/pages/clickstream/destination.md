---
layout: page
hide: true
title: Create a Clickstream Destination
permalink: /clickstream/destination/
order: 1
---

Clickstream Integration Development Process

## Overview

### Description

One-time setup tasks are for a dev onboarding to integrations.  Everything that follows is the process for developing each integration.  The tasks in here are the (previously undocumented) process of how we actually do this today.  There’s definitely room for improvement in our stack and automation in our toolchain.

### Purpose

The goal is to make one definitive comprehensive checklist for developing any integration, client side or server side, original source or fork, etc.  The purpose is to simplify and optimize the process for the developer by giving them clearly defined tasks and other stakeholders visibility into the process.

## One-time Setup

1. **Create account on the Astro front end app.** For both staging and prod.
	- If you need to access customer’s orgs in prod, Andrew can make you a super admin.
1. **Discuss with Andrew how the v1 + v2 Mongo schemas are defined and used by the front end and API.**  Providers, connections, clickstream configs, etc.
	- We might have a schema diagram of this somewhere.
1. **Get access to internal toolchain and services.**  GitHub, Mongo, DC/OS, CircleCI, internal Redshift, etc.
	- Fastest way — ask someone who already has it.  Each project has specific resources too but these are used across most / all.

## Integration Setup

1. **Get access to required external services for integration.  Have customer configure any required settings if we can’t modify ourselves.**  This depends on each integration but for example, ask the customer to add our devs to their DoubleClick account in staging + prod for an enterprise-y integration.  For simpler integrations, we can make our own trial / free accounts.  If we can’t get either, we can reach out to the company and explain what we’re building to try to get special access.
	- It’d be nice to have one dev@astronomer.io account used universally but today people mostly make one offs with their personal accounts.
1. **Get access to required internal resources.**  For example, every server-side integration requires a Kinesis stream on AWS to be created by the infrastructure team which also requires an IAM user + policy.  Many integrations need access to S3, RDS, Redshift, or other Amazon services.
	- Your integration may require additional downstream services as well.  Ask Ken or Will to create and grant access.
1. **Get creds for above external & internal services.  API keys, secrets, etc.**
	- Ideally all of this is in place after the scope request phase and before starting the dev work phase to reduce the number of blockers during dev time.
1. **Test the creds.**

## Config

1. **Define shape and schema of connection, config, and provider.**  This can be more time consuming than it sounds.  We typically iterate on these during the course of development.
	- Aim for API consistency with Segment.  If the integration is a Segment fork, look at their unit tests and reverse engineer their config structure.  If the integration is a source, we encourage consistency with our other integrations — look at recent clickstreamConfigs for examples.
1. **Create connection config and clickstream config(s) in staging for testing purposes.**
	- Use the web app over Mongo directly if possible to mirror a customer’s usage.  Not always possible in advanced use cases.

## Development (source)

1. **Write the code. ;)**
	- Follow naming conventions of similar integration repos.

## Development (fork)

1. **Fork the Segment repo into astronomer-integrations.**  Make code changes if expansion / modifications are required to support our use case.

## Testing

1. **Write unit tests if you have time.**  Writing smaller functions makes this easier and eases or avoids having to refactor later.  Use mocking for service unit tests.
	- We don’t do as much automated testing today as we would like.  Most of our components are based around APIs or external services which adds complexity to unit testing.  Typically we do more manual testing.  We could benefit from creating follow up issues for this or committing time to it.
1. **Run linter.**

## Deployment - Dev / Staging (destinations)

1. **Create the service in DC/OS using JSON config.**  Copy the template from a similar service and modify as needed.
	- Example: For a Kinesis destination, name the worker “integration-worker-kinesis”.
1. **Deploy integration in DC/OS staging.**  We do manual integration testing on staging with the deployment.  Re-deploy as needed.
	- Some bugs can be caught on in our dev environment but we do not have a true staging environment that mirrors all services in prod.  Debugging mostly needs to happen in prod today.
1. **Test that code runs successfully end-to-end.**

## Deployment - Prod (destinations)

1. **Create connection config and clickstream config(s) in prod.**  Use real creds if we have them; otherwise, copy configs from staging.
	- Some values like app IDs will be different in prod.
1. **Deploy integration in DC/OS prod.**  Mostly copy the staging config but resource requirements (CPU, memory, etc) are different in prod.  Look at similar configs in prod.
1. **Test that code runs successfully end-to-end.**
	- Don’t assume it will work in prod because it worked in dev.  In prod, there are edge cases and the environment is more complex, more demand on resources, etc.
1. **Performance testing.**
	- Typically we solve scaling challenges by using more efficient algorithms or increasing cluster resource allocation.

## Docs - Internal

1. **Write one-line docstrings on major classes and functions.**
	- We write some internal docs today, mostly code comments.

## Docs - External

1. **Write basic docs.**
	- Ideally external docs describe: (1) how a customer sets up the service, (2) how they configure the service, (3) how they configure our app for the service.  We do some of this today but outside of the dev cycle.  Example from Segment: Amazon Kinesis Destination.

## Code Review

1. **Open a PR requesting code review.**  Include your timeline for the reviewer if urgent or high priority.  Mark the reviewer as both “assigned to” and “reviewer”.
	- If possible assign to someone who’s knowledgeable on that codebase + has availability.

## Cleanup

1. **Migrate data in config database.** If this integration deprecated a previous version or made config variables obsolete, clean that up by migrating and removing any old configs.  Check Mongo for how many and which customers are impacted.
	- If you have time, do cleanup tasks during integration dev; otherwise, spin off as separate internal follow up issue to reduce tech debt.
1. **Request an integration icon.**  Open a ticket for front end to add an icon to the UI for this integration if it has the generic one.

---

## Process

1. Write + test code for integration, if it doesn't exist yet.
2. If serverside, start up an integration worker process in your Astronomer instance.
3. Add record in MongoDB so you can turn on integration in Galaxy UI.
4. Enable integration for an app, confirm data is flowing end-to-end.

## Client Side

* {add checklist}

## Server Side

* {add checklist}

## Mobile

* {add checklist}
