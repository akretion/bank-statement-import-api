#!/bin/bash
set -Eeuo pipefail

# On github, when running oca-repo-addons-template, if some modules
# are hard to install (because of complex and long test-requirements.txt)
# you may just skip them in tests.
# Yes I know it's sad to not test everything from a ci, but one may run the tests
# elsewhere (local, project)

# hide all not testable addons

# -not -path './*.' remove dots files
# -maxdepth 1 no recursive search
# -typ d only dirs

if [ ! -f no-tests.regex ] ; then
	echo "no-tests.regex not found"
	exit 1
fi

if [ $(cat no-tests.regex | wc -w) -eq 0 ] ; then
	# no-tests is empty no need to continue
	exit 0
fi

if [ -z "${GITHUB_WORKSPACE:-}" ] ; then
	find -maxdepth 1 -type d -not -path './.*' | grep --invert-match -f no-tests.regex | git sparse-checkout set --stdin
else
	find -maxdepth 1 -type d -not -path './.*' | grep -f no-tests.regex | xargs rm -rf
fi
