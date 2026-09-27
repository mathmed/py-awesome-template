# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                 |    Stmts |     Miss |    Cover |   Missing |
|--------------------------------------------------------------------- | -------: | -------: | -------: | --------: |
| app/common/logger.py                                                 |       16 |        0 |     100% |           |
| app/common/settings.py                                               |       19 |        0 |     100% |           |
| app/domain/contracts/example\_database\_contract.py                  |        3 |        0 |     100% |           |
| app/domain/contracts/usecase.py                                      |        7 |        0 |     100% |           |
| app/domain/entities/models/base\_model.py                            |        3 |        0 |     100% |           |
| app/domain/entities/models/example\_model.py                         |        2 |        0 |     100% |           |
| app/domain/errors/domain\_errors.py                                  |        8 |        0 |     100% |           |
| app/domain/usecases/example/example\_usecase.py                      |       11 |        0 |     100% |           |
| app/infra/database/example\_database.py                              |        8 |        0 |     100% |           |
| app/main/main.py                                                     |        6 |        0 |     100% |           |
| app/presentation/factories/example\_factory.py                       |        4 |        0 |     100% |           |
| app/presentation/fastapi/configs/configs.py                          |       16 |        0 |     100% |           |
| app/presentation/fastapi/handlers/domain\_error\_handler.py          |       10 |        0 |     100% |           |
| app/presentation/fastapi/middlewares/request\_logging\_middleware.py |       11 |        0 |     100% |           |
| app/presentation/fastapi/routes/example\_routes.py                   |        7 |        0 |     100% |           |
| app/presentation/fastapi/routes/health\_routes.py                    |        5 |        0 |     100% |           |
| **TOTAL**                                                            |  **136** |    **0** | **100%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/mathmed/py-awesome-template/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/mathmed/py-awesome-template/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fmathmed%2Fpy-awesome-template%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/mathmed/py-awesome-template/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.