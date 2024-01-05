# Start project in development mode
dev:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up

# Start project in development mode with rebuild
dev-build:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up --build

# Run unit tests in docker container
test:
	docker exec -it py-awesome-template sh -c "cd /home/app && poetry run pytest --cov-config=.coveragerc --cov-report html --cov=. app/"

# Verify if styles (PEP8) is correct
check-code:
	docker exec -it py-awesome-template sh -c "cd /home/app && poetry run flake8 .; poetry run pylint app/ --disable=all --enable=e,f; poetry run isort --check-only ./app"

# Format code to PEP8
format-code:
	docker exec -it -e UID=$(id -u) -e GID=$(id -g) py-awesome-template sh -c "cd /home/app && poetry run autopep8 --exclude="main.py" .; poetry run isort . && chown -R $(id -u):$(id -g) ."
