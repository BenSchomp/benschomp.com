# benschomp.com

The public pages of benschomp.com, plus the projects listed in `projects.json`,
which are built from their own repos on every deploy.

This folder can sit on top of a full copy of the DreamHost site. `.gitignore`
ignores everything except the public pages, so only those are tracked and uploaded.
Deploys only add or update files. They never delete anything on the server.

## Preview locally

```sh
python3 deploy.py build --use-local-clones   # builds projects from your own clones (local_clone_path)
python3 -m http.server --directory _site     # then open http://localhost:8000
```

Leave out `--use-local-clones` to build each project from the latest commit on GitHub,
as a real deploy does. `resume/index.php` is a PHP redirect, so it only works on DreamHost.

## Deploy

Push to `main`. GitHub Actions builds the site and uploads it. You can also run it by hand
from the Actions tab ("Run workflow"), with a dry run option that lists what would change.

To deploy from your Mac instead:

```sh
DEPLOY_SSH_TARGET=user@server.dreamhost.com DEPLOY_REMOTE_PATH=benschomp.com/ python3 deploy.py upload --dry-run
```

## Add a project

Add an entry to `projects.json`: its repo, `git_ref`, local clone path, install and build
commands (both optional), the folder the build writes to (`.` for plain static files),
and the folder name to publish it under.

`git_ref` is a branch to deploy the latest work (Yoshi uses `master`), or a tag to pin
a version (Viktory Calc uses `live-2016`). To promote a new version of a pinned project,
tag it in its repo and change `git_ref` here.
Then link to it from `index.html` if you want.

## One-time setup for GitHub Actions

1. Make a key just for deploys, with no passphrase:
   `ssh-keygen -t ed25519 -N "" -f ~/.ssh/benschomp_deploy`
2. On DreamHost, add the public key to `~/.ssh/authorized_keys`, locked to the site folder
   with `rrsync`, so the key can only rsync into `~/benschomp.com/` and nothing else:

   ```
   command="rrsync ~/benschomp.com",restrict ssh-ed25519 AAAA... benschomp-deploy
   ```

   If `rrsync` isn't on the server's PATH, it usually ships with rsync's docs,
   for example `/usr/share/doc/rsync/scripts/rrsync`. Copy it to `~/bin/` and make it executable.
3. In the GitHub repo, under Settings > Secrets and variables > Actions, add:
   - `DEPLOY_SSH_PRIVATE_KEY`: the contents of `~/.ssh/benschomp_deploy`
   - `DEPLOY_SSH_TARGET`: your DreamHost `user@server`
   - `DEPLOY_SSH_KNOWN_HOSTS`: the output of `ssh-keyscan <server>`
4. Run the workflow by hand with dry run checked, and read the list before the first real deploy.
