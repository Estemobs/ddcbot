#!/usr/bin/env bash
set -euo pipefail

cd /repo
git config --global --add safe.directory /repo

BRANCH="${GIT_BRANCH:-master}"
INTERVAL="${CHECK_INTERVAL:-60}"

echo "[updater] surveillance de la branche '${BRANCH}' toutes les ${INTERVAL}s"

while true; do
    git fetch --quiet origin "${BRANCH}" || echo "[updater] échec du git fetch, nouvelle tentative dans ${INTERVAL}s"

    LOCAL_REV="$(git rev-parse HEAD || echo local)"
    REMOTE_REV="$(git rev-parse "origin/${BRANCH}" 2>/dev/null || echo unknown)"

    if [ "${LOCAL_REV}" != "${REMOTE_REV}" ] && [ "${REMOTE_REV}" != "unknown" ]; then
        echo "[updater] nouvelle version détectée (${LOCAL_REV:0:7} -> ${REMOTE_REV:0:7}), mise à jour..."
        git merge --ff-only "origin/${BRANCH}"
        docker compose build ddcbot
        docker compose up -d ddcbot
        echo "[updater] bot redémarré sur ${REMOTE_REV:0:7}"
    fi

    sleep "${INTERVAL}"
done
