# CHANGELOG


## v1.2.0 (2026-10-03)

### Bug Fixes

- Enforce per-artist track limits across all fallback stages
  ([`1f21ddd`](https://github.com/ZyanKLee/crateport/commit/1f21ddd25f121b0e0c0432baa65ed91e510119c1))

- Load full artist data with fan counts for disambiguation
  ([`98482f5`](https://github.com/ZyanKLee/crateport/commit/98482f5baca5941150bbc7fe50551ba57b62c24c))

- Show interactive choice every time when multiple artists exist with -i flag
  ([`28ee720`](https://github.com/ZyanKLee/crateport/commit/28ee720f340790e19f7ca3b94350a2e55e76fab2))

### Features

- Add album-based fallback for artist track discovery
  ([`08b122b`](https://github.com/ZyanKLee/crateport/commit/08b122b2cdd41ee38afab1d5d5ffce5e54e03581))

- Add fuzzy matching for artist search with user confirmation
  ([`d42386e`](https://github.com/ZyanKLee/crateport/commit/d42386edbcf2599a4f87a334fc7a88b5ce12c02a))

- Add interactive artist disambiguation for name collisions
  ([`9c2c195`](https://github.com/ZyanKLee/crateport/commit/9c2c195b4613de3e0dc98e669e668c27c6dd8378))

- Add search_tracks_by_artist for broader track lookups
  ([`1fed09d`](https://github.com/ZyanKLee/crateport/commit/1fed09d5018c83276724e14d3a84ec6ca98cd315))

- Improve artist track resolution with fallback search for collaborations
  ([`d85dd70`](https://github.com/ZyanKLee/crateport/commit/d85dd706032c06da69370bb1796a3fded29b5386))

- Select most popular artist when multiple exact name matches exist
  ([`e2014d8`](https://github.com/ZyanKLee/crateport/commit/e2014d8de53d803af69d766fddc37f436a3281b9))

- Show track count per artist/album during playlist generation
  ([`2a843a1`](https://github.com/ZyanKLee/crateport/commit/2a843a1e7345c5a47b1bcce924612820fa2d23e3))

### Refactoring

- Implement ID-based artist caching for robust name disambiguation
  ([`a6e006b`](https://github.com/ZyanKLee/crateport/commit/a6e006b9def17f8f327c3cd882fda417b136a6d9))


## v1.1.0 (2026-05-10)

### Chores

- **deps**: Update dependencies in pyproject.toml
  ([`875e490`](https://github.com/ZyanKLee/crateport/commit/875e49075dc93ce48848b6a2bed6edccd5e9733e))

### Features

- Add Git hooks management with Lefthook and update dependencies
  ([`404ac8c`](https://github.com/ZyanKLee/crateport/commit/404ac8c5a567b24fbf2c9ae1aad78ebdafee7032))

- Add option to always select the first candidate in ISRC resolution
  ([`9ac7893`](https://github.com/ZyanKLee/crateport/commit/9ac78939906eaf4a604783f6abd18239db2066cc))

- Add timeout error handling for Deezer and MusicBrainz API requests
  ([`6cd7028`](https://github.com/ZyanKLee/crateport/commit/6cd702836c9fbe97275fc867f8aa0a09a90b79ce))

- Implement ISRC resolution and CSV parsing/writing for VirtualDJ and Soundiiz
  ([`da2aae5`](https://github.com/ZyanKLee/crateport/commit/da2aae5fedae51161079afaa79e44766fe3d210a))


## v1.0.3 (2026-03-13)


## v1.0.2 (2026-03-13)

### Features

- Add GitHub Actions workflow for automated PyPI releases
  ([`77a1885`](https://github.com/ZyanKLee/crateport/commit/77a188587725710b1bdda714b6bb74a723838077))


## v1.0.1 (2026-03-13)

### Chores

- Downgrade version to 1.0.0 and add .envrc to .gitignore
  ([`ce75cf7`](https://github.com/ZyanKLee/crateport/commit/ce75cf7f11a3c45a2bcb8e4646470e62ca8e7dba))

- Update CHANGELOG generation method and versioning
  ([`1bd4317`](https://github.com/ZyanKLee/crateport/commit/1bd431761543b185c7adf9adf80cedfe27dbf551))

- Update semantic release changelog configuration and templates
  ([`5e650e4`](https://github.com/ZyanKLee/crateport/commit/5e650e4af86b622427244b9493318c85c08a1267))

### Documentation

- Add release process and commit message guidelines to CONTRIBUTING.md
  ([`24dfe40`](https://github.com/ZyanKLee/crateport/commit/24dfe402b30120dd54f0f9cc5da8ac18c90c1af3))


## v1.0.0 (2026-03-13)

### Bug Fixes

- **deezer**: Require exact matches for artists, albums, and tracks
  ([`64999c6`](https://github.com/ZyanKLee/crateport/commit/64999c6208013257c208d770a0c5afb3b19850cf))

### Chores

- Add LICENSE, CHANGELOG, scripts, and update project config
  ([`ec2dd9e`](https://github.com/ZyanKLee/crateport/commit/ec2dd9eea06888c811fd635f68b544cbcdebd652))

- Initial commit
  ([`f5ce1b6`](https://github.com/ZyanKLee/crateport/commit/f5ce1b67834f18779c1bde6d034a19760098bbed))

- Make tool installable via pipx
  ([`9bb38f0`](https://github.com/ZyanKLee/crateport/commit/9bb38f0a43786b01bf425e8225dd462b09ad170e))

- **dev**: Add VS Code extensions for dev container
  ([`dfd980d`](https://github.com/ZyanKLee/crateport/commit/dfd980dac66c778f0772fd518cab04b578ef98a7))

### Documentation

- Add CONTRIBUTING.md and improve generate/convert command docs
  ([`7a96001`](https://github.com/ZyanKLee/crateport/commit/7a96001544174a3e8badad7e82bcb2794c3816bb))

- Add links to generate and convert command docs in README
  ([`abf8691`](https://github.com/ZyanKLee/crateport/commit/abf8691922cc4327882d85724f16252103e46290))

- Clarify usage instructions and command descriptions in README
  ([`da24506`](https://github.com/ZyanKLee/crateport/commit/da245061cee6454a2860b0b27ebabecbdb5a71df))

- Restructure CHANGELOG and update cliff.toml template for clarity
  ([`f3d6e02`](https://github.com/ZyanKLee/crateport/commit/f3d6e0207499502ce0c3697843df2381d1193fa9))

- **config**: Clarify working directory structure and path handling
  ([`30439ba`](https://github.com/ZyanKLee/crateport/commit/30439ba0f16bac30846df7d7e882375e8cbca3d1))

### Features

- Add MusicBrainz client for fallback artist resolution
  ([`78543fb`](https://github.com/ZyanKLee/crateport/commit/78543fb6791332220712c92c17596b3bb438e748))

- **cli**: Add subcommands for playlist generation and conversion
  ([`0512593`](https://github.com/ZyanKLee/crateport/commit/051259322503a5532e98ae38ffd3ce36fd2af0d5))

### Refactoring

- Improve code readability and maintainability
  ([`2c33b79`](https://github.com/ZyanKLee/crateport/commit/2c33b79f2662ac49a9613de5a9e8898be8d7bb64))

- Rename project from playlist-generator to crateport
  ([`2090ebd`](https://github.com/ZyanKLee/crateport/commit/2090ebdee27a97ae971ad4e8ad37303c8913884d))
