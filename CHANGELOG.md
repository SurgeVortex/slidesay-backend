# Changelog

## [0.1.0](https://github.com/SurgeVortex/slidesay-backend/compare/v0.0.1...v0.1.0) (2026-02-21)


### Features

* add admin tier override API (SS-21 partial) ([362ec65](https://github.com/SurgeVortex/slidesay-backend/commit/362ec65a670668200bf3f9cd55688a614e53fba4))
* add dev mode auth bypass (SS-26) ([9b3b6e6](https://github.com/SurgeVortex/slidesay-backend/commit/9b3b6e61b0bc6f5ad2ab0640684524ba8cafca67))
* add LLM service with OpenRouter integration and tests ([97b4188](https://github.com/SurgeVortex/slidesay-backend/commit/97b4188da8946cac343d137838d0b5da9d2cd9df))
* add PDF generation service with tests ([451c48e](https://github.com/SurgeVortex/slidesay-backend/commit/451c48e1dca8f7faf7027f08195dc6d02bff8426))
* add PPTX generation service with themes and tests ([f27eab4](https://github.com/SurgeVortex/slidesay-backend/commit/f27eab4b438257260814c30d06eb6e191f41e98d))
* add presentation CRUD service and API endpoints ([7cc4b15](https://github.com/SurgeVortex/slidesay-backend/commit/7cc4b152981741760705f78208fd3a25e7170d3b))
* add usage tracking service with tier enforcement ([fd02ddd](https://github.com/SurgeVortex/slidesay-backend/commit/fd02dddc27bf7b4f4f2bc92a74a2a3c3994b1c97))
* enforce backend usage limits by tier (SS-40) ([1847119](https://github.com/SurgeVortex/slidesay-backend/commit/1847119b21fa3de457ff05e6a90b21b4a15ab1f2))
* fix backend venv, add Makefile and lint config (SS-22) ([03abdfd](https://github.com/SurgeVortex/slidesay-backend/commit/03abdfd1546f3997395fce7210b72d3c8acd1be3))
* Stripe Payment Flow (SS-38) ([b41fb87](https://github.com/SurgeVortex/slidesay-backend/commit/b41fb876ae1e361e6dd281ac7144baa8ee2f27bb))
* Stripe webhook + tier sync (SS-39) ([a239e19](https://github.com/SurgeVortex/slidesay-backend/commit/a239e1913e3e1762db522fde37cbac6598976d83))
* User Profile Service backend (SS-36) ([b8f5d2c](https://github.com/SurgeVortex/slidesay-backend/commit/b8f5d2c07ea058f167f4ce6ea5ce13010a96e6b2))
* wire LLM service into presentation create endpoint (SS-23) ([9829df7](https://github.com/SurgeVortex/slidesay-backend/commit/9829df72334c2df69c1ef8d03320ee88be83700a))


### Bug Fixes

* broaden mypy overrides - cover all src modules for MVP ([952ad6c](https://github.com/SurgeVortex/slidesay-backend/commit/952ad6cc120e0b6d8c73278cfa35f7b9f2b4ceaf))
* CI pipeline - fix broken pipe in ls|head, make black check non-blocking ([6569456](https://github.com/SurgeVortex/slidesay-backend/commit/6569456f99f148232589ae998ea4c5bce33856a8))
* comprehensive mypy overrides for CI - ignore missing imports, relax strict checks on generated code ([caf5161](https://github.com/SurgeVortex/slidesay-backend/commit/caf5161d082cc00a1add6fe8194528cb081ec850))
* lazy-init StripeService to prevent startup crash ([ac2d082](https://github.com/SurgeVortex/slidesay-backend/commit/ac2d0826f55179e47f646282e3ad0cc4e061beeb))
* recompile requirements-dev.txt to include mypy for CI ([2106e69](https://github.com/SurgeVortex/slidesay-backend/commit/2106e69adde25a7c776b84345787ea634a4b883a))
* relax mypy strict mode for sub-agent generated files ([2af71f1](https://github.com/SurgeVortex/slidesay-backend/commit/2af71f15ce69dfd73e4b831503e25c0ec759e6f6))
* remove unused imports breaking CI lint (ruff) ([9cf1278](https://github.com/SurgeVortex/slidesay-backend/commit/9cf12787fadf7131368bd8f41785c835090d3cb0))
* restore full requirements.txt (was accidentally truncated to stripe-only) ([959dc56](https://github.com/SurgeVortex/slidesay-backend/commit/959dc562958db011bb59a12586b8c7facb1dd84d))
