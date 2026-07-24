"""Central code-version marker and config compatibility contract.

Why: guidelines §8.1 require an explicit code version starting at 1.00,
validated against config-file versions at startup and reported in the Step-0
declaration (book rule 53). The supported-config tuple is the single place a
new config schema version gets admitted.
"""

CODE_VERSION = "1.00"

# Config files whose "version" key is outside this tuple are rejected at
# startup (FR-CFG-2) — better a loud boot failure than a silent drift mid-match.
SUPPORTED_CONFIG_VERSIONS: tuple[str, ...] = ("1.00",)
