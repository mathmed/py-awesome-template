# Start project in development mode
dev:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up

# Start project in development mode with rebuild
dev-build:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up --build

# Run unit tests in docker container
test:
	docker exec -it py-awesome-template sh -c "cd /home/app && uv run pytest --cov-config=.coveragerc --cov-report html --cov=. app/"

# Verify if styles (PEP8) is correct
check-code:
	docker exec -it py-awesome-template sh -c "cd /home/app && uv run flake8 .; uv run pylint app/ --disable=all --enable=e,f; uv run isort --check-only ./app"

# Format code to PEP8
format-code:
	docker exec -it py-awesome-template sh -c "cd /home/app && uv run autopep8 --exclude="main.py" .; uv run isort ." && sudo chown -R $(id -u):$(id -g) .
