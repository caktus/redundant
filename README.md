# redundant

redundant is a linter for project wide technical debt.

Currently, the main goal is to identify duplicate and near-duplicate code.
While redundant was built with Django projects in mind, and to that end can
analyze python, javascript, html, and css files, it should be useful for
many types of codebases.

## Usage

Simple run redundant in the top-level directory of your project and let it
run. For larger projects it can take a while.

    ./path/to/redundant.py

You can improve how it runs by adding a `.redundantrc` to your project. See
the `dotredundantrc` file for an example. Excluding vendor files, especially
minimized code, can improve run time significantly.

You can configure the threshold for duplicate detection by changing the
`diff-delta-max` setting in the `[report]` section of the config.
