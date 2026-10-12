# Campus template operation

The People category copies whichever campus is installed in
`world-templates/hill_people_template/` under the Paper server directory. The
current handoff is the V29 exterior draft. A campus revision is an asset choice,
not a code version pin.

Follow the [Windows asset instructions](operations/windows-assets.md) or
[Linux deployment guide](operations/deployment.md). Stop Paper, preserve the
previous template, and replace the entire folder with the new one. Do not merge
region files from two revisions. The folder must directly contain `region/`;
the plugin does not extract archives or search through nested world folders.

Prepared campus packages include `hill-campus-template.yml`, which carries the
bounds and spawn copied into each new participant world. Optional POI files are
supported. No particular revision, region-file count or archive filename is
required. The updated plugin ignores the old file-count settings.

New People entries and explicit owner-confirmed resets use the installed folder.
Existing participant worlds are preserved; changing the template is not a
migration. A reset deliberately replaces the selected entry's build, so it
remains an owner-confirmed game operation.

Keep `people.require-template: true` and `people.structure-file: ""` for this
folder-based deployment. Missing or invalid templates block creation/reset
instead of silently substituting flat terrain. The plugin does not update the
template from GitHub; operators control the files in this directory.

Use [the smoke guide](SMOKE_TEST.md) for game checks and
[the player guide](operations/player-guide.md) for camera and entry commands.
