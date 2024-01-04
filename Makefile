# Start project in development mode
dev:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up

# Start project in development mode with rebuild
dev-build:
	docker compose --env-file=.env -f ./docker/docker-compose.yaml up --build
