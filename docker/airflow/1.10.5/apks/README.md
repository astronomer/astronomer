Precompiling Python packages
============================

This folder contains Alpine packages for slow-to-compile python modules.

The `repo/` folder contains output package files. These binary package files are stored in [LFS](https://help.github.com/en/github/managing-large-files/about-git-large-file-storage) so that `git clone` isn't to slow. When building the docker image these are installed via HTTP in our Dockerfile (i.e. not copied in via `COPY`).

## Building packages

Running `make` in this folder should rebuild all that is needed. The only requirements are `openssl` (to generate a signing key), and `docker`.

We don't commit the private key, so each time we need to build new packages we will generate a new keypair if one is not found. (This is fine, as we don't leave the image with our repo configured, so we don't ever push out updates that we expect `apk update` to pick up.)

## Updating a package

If we need to update to a new version of one of the packages there are two ways it can be done:

1. Get the latest build file from Alpine directly:
    1. Go to pkgs.alpinelinux.org and search for the package we want, for example `*bcrypt*`.
    2. Click on the package name
    3. Click on "Git repository" and replace the APKBUILD in our folder with the latest one.
2. To update a version manually, edit the APKBUILD file:
    1. Set `pkgver` to the latest relese
    2. Set `pkgrel` back to 0
    3. Update the `sha512sums` line, for example: `curl -fsSL https://github.com/pyca/bcrypt/archive/3.1.7.tar.gz | shasum -a 512`

Once that is done `make` should notice the change and rebuild the package.
