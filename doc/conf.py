import os

# Configuration file for the Sphinx documentation builder.

project = "PyDotBot"
copyright = "2023, Inria"
author = "Alexandre Abadie"

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.githubpages",
    "sphinx.ext.graphviz",
    "sphinx.ext.inheritance_diagram",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
]

tls_verify = False
templates_path = ["_templates"]
exclude_patterns = ["_build"]
nitpick_ignore_regex = [
    ("py:class", r"abc.*"),
    ("py:class", r"enum.*"),
    ("py:class", r"numpy.*"),
    ("py:class", r"pydantic.*"),
    ("py:class", r"pynput.*"),
    ("py:class", r"threading.*"),
    ("py:class", r"starlette.*"),
    ("py:class", r"ConfigDict"),
    ("py:class", r"DotenvType"),
    ("py:class", r"FieldInfo"),
    ("py:class", r"Path"),
    ("py:class", r"SettingsConfigDict"),
    ("py:class", r"<MagicMock.*>"),
    ("py:class", r"ComputedFieldInfo"),
]

# -- Options for HTML output -------------------------------------------------

html_theme = "pydata_sphinx_theme"
html_sourcelink_suffix = ""
html_static_path = ["_static"]

myst_enable_extensions = ["html_image"]

# Define the json_url for our version switcher.
json_url = "https://pydotbot.readthedocs.io/en/latest/_static/switcher.json"
rtd_version = os.environ.get("READTHEDOCS_VERSION")
rtd_version_type = os.environ.get("READTHEDOCS_VERSION_TYPE")
rtd_git_identifier = os.environ.get("READTHEDOCS_GIT_IDENTIFIER")
# If READTHEDOCS_VERSION doesn't exist, we're not on RTD
# If it is an integer, we're in a PR build and the version isn't correct.
# If it's "latest" → change to "dev" (that's what we want the switcher to call it)
if not rtd_version or rtd_version.isdigit() or rtd_version == "latest":
    rtd_version = "dev"
    json_url = "_static/switcher.json"
elif rtd_version == "stable":
    rtd_version = f"{rtd_git_identifier}"
elif rtd_version_type == "tag":
    rtd_version = f"{rtd_git_identifier}"

html_theme_options = {
    "external_links": [
        {
            "url": "https://github.com/DotBots/DotBot-firmware",
            "name": "DotBot firmware",
            "attributes": {
                "target": "_blank",
                "rel": "noopener me",
            },
        },
        {
            "url": "https://github.com/DotBots/DotBot-hardware",
            "name": "DotBot hardware",
            "attributes": {
                "target": "_blank",
                "rel": "noopener me",
            },
        },
    ],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/DotBots/PyDotBot",
            "icon": "fa-brands fa-github",
        },
    ],
    "header_links_before_dropdown": 3,
    "logo": {
        "text": "PyDotBot",
    },
    "navbar_align": "left",
    "navbar_center": ["version-switcher", "navbar-nav"],
    "switcher": {
        "json_url": json_url,
        "version_match": rtd_version,
    },
    "footer_start": ["copyright"],
    "footer_center": ["sphinx-version"],
}

# -- Options for linkcheck ---------------------------------------------

linkcheck_ignore = [r"http://localhost:\d+/"]

# -- Options for autosummary/autodoc output -----------------------------------
autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "groupwise"
