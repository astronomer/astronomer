<!--
Please fill out the sections below, deleting anything that is irrelevant or empty.
-->


## Description

<!--
Describe the purpose of this pull request.
-->

## PR Title

<!--
Please make the PR title informative to the user experience. For example when adding a feature, say "Add metrics tab for Deployments" instead of "Bump Astro-UI to version X.Y.Z". Bugs are sometimes harder to make customer-facing because they are very detailed, but do what you can. Instead of "Fix metrics cardinality bug" (user does not know what 'cardinality' means and does not matter to them), say "Fix bug slowing down the metrics tab". The PR title will be used for the commit message when it's merged, and these commit messages are used to generate customer-facing release notes.

If there is only one commit in the PR, when clicking the merge button, be sure to copy the PR title into the PR squash and merge option's commit message. By default with a single commit, it will use the commit message instead of the PR title.
-->

## 🎟 Issue(s)

<!--
Resolves astronomer/issues#XXXX
-->

## 🧪  Testing

<!--
What are the main risks associated with this change, and how are they addressed by tests added in this PR?

Please add helm unit testing, if applicable. The docs are regretfully sparse for helm unit testing, [here](https://github.com/quintush/helm-unittest/blob/master/DOCUMENT.md) is what we have to work with. In general, these kind of tests can be used for specific assertions like 'when these values are set, the resource ends up looking like XYZ' but not for generalized assertions like 'for all resources, make sure the namespace is not set to the release name'.

Please also add to the system testing [here](../bin/functional-tests), if applicable. This kind of testing allows you to connect into any live, running pod to make assertions about how they are operating. For example, one test connects to a Prometheus pod, queries the Prometheus API, and makes assertions about the Prometheus scrape targets being healthy.
-->

## 📸 Screenshots

<!--
Add screenshots to illustrate the changes, if applicable.
-->

## 📋 Checklist

- [ ] The PR title is informative to the user experience
