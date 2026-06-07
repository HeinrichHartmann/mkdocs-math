import os
import logging
import requests
import tempfile
from mkdocs.config.defaults import MkDocsConfig


# Grab a logger
log = logging.getLogger("mkdocs.plugins.math")


def tempfile_from_url(name: str, url: str, suffix: str) -> str:
    """Download bibfile from a URL."""
    log.debug(f"Downloading {name} from URL {url} to temporary file...")
    for i in range(3):
        try:
            dl = requests.get(url)
            if dl.status_code != 200:  # pragma: no cover
                raise RuntimeError(f"Couldn't download the url: {url}.\n Status Code: {dl.status_code}")

            file = tempfile.NamedTemporaryFile(mode="wt", encoding="utf-8", suffix=suffix, delete=False)
            file.write(dl.text)
            file.close()
            log.info(f"{name} downloaded from URL {url} to temporary file ({file})")
            return file.name

        except requests.exceptions.RequestException:  # pragma: no cover
            pass
    raise RuntimeError(f"Couldn't successfully download the url: {url}")  # pragma: no cover


def get_path_relative_to_mkdocs_yaml(path: str, config: MkDocsConfig) -> str:
    """Get the relative path of a file to the mkdocs.yaml file."""
    mkdocs_rel_path = os.path.normpath(os.path.join(os.path.dirname(config.config_file_path), path))
    return mkdocs_rel_path
