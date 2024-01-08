[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Vulnerabilities](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=vulnerabilities)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Bugs](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=bugs)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Code Smells](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=code_smells)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=py-awesome-template&metric=coverage)](https://sonarcloud.io/summary/new_code?id=py-awesome-template)

# py-awesome-template

Base template to start new awesome Python3.x projects. This template includes:

- Folder structure based on Clean Architecture with some initial examples
- Code styles pre-configuration: pylint, autopep8, flake8 and isort
- SonarCloud base configuration for code analysis
- CI (Github Actions) base configurantion with: code styles, unit tests and sonar scan jobs
- Docker configuration to run project locally

## Setup project

### Docker

To run the project locally, you need to get Docker. You can install Docker [following this tutorial](https://docs.docker.com/engine/install/).

### Sonar Config

To analysis the code on each git push, you need to configure the SonarCloud (its free for personal use with public repositories). On [SonarCloud](https://sonarcloud.io/), create a new project using Github Actions. Take the **SONAR_TOKEN** and create a secret with the same name on your Github repository. Then, fill the `sonar-project.properties` file with your `sonar.projectKey` and `sonar.organization`; both are shown on the SonarCloud configuration page.

### Installing Dependencies

To install a new dependency on project use the `pyproject.toml` file. Use the `[tool.poetry.dependencies]` to add production dependencies and `[tool.poetry.group.test.dependencies]` to add test and development dependencies.

### Available commands

On root folder, you can run some commands using **make**.

| Command          | Description                                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| make dev         | Runs the project locally. It is necessary to have Docker installed for it to work.                                                                     |
| make dev-build   | Runs the project locally performing the build. Useful for when a new dependency is installed. It is necessary to have Docker installed for it to work. |
| make test        | Run unit tests. The docker container must be running to work.                                                                                          |
| make check-code  | Verify the code sintax and styles (PEP8). The docker container must be running to work.                                                                |
| make format-code | Format the code styles (PEP8). The docker container must be running to work.                                                                           |

### Config files

| File                     | Description                                                                                         |
| ------------------------ | --------------------------------------------------------------------------------------------------- |
| .coveragerc              | Defines files that will be analyzed and ignored in test coverage reports.                           |
| .env.example             | Defines the enviroment variables. Need to create a .env file on root project from the .env.example. |
| .flake8                  | Defines flake8 code styles.                                                                         |
| Makefile                 | Create shortcuts for commands using make.                                                           |
| pyproject.toml           | Set project details, add dependencies, define autopep8, pylint and isort configurations.            |
| sonar-project.properties | Set the SonarCloud configs.                                                                         |
| pytest.ini               | Set pytest configs.                                                                                 |
| github/workflows/ci.yaml | Github Actions CI configuration file.                                                               |

## Architecture and folder structure

![Alt text](docs/arc.png "Clean Architeture")

This template uses an architecture and folder structuring based on uncle bob's clean architecture.
layers (folders) have the following responsibilities:

### Main

Basic settings and starting point. Here the "app" is created.

### Domain

The most important layer of the project. Use cases, models and entities, services (common codes) and contracts are written in this layer. Contracts are interfaces that abstract some external library or service, which will be written in the infrastructure layer. The domain layer should never access other layers directly, only through interfaces using dependency injection.

### Presentation

Layer where the means to access the application's use cases and expose the application to the external world are created, through HTTP/REST, for example. Here frameworks can be used for this, such as FastAPI or Flask. In the presentation layer, the factory pattern is also used, which is used to instantiate all the classes necessary to execute a use case.

### Infra

Integrations with any API, library or service external to the application are implemented here. To do this, the integration implementation class must follow a contract defined at the domain layer.
