@echo off
setlocal ENABLEDELAYEDEXPANSION
chcp 65001 >nul

REM === Usage and argument handling ===
set "ENV=%~1"
if "%ENV%"=="" (
  echo ⚠️  No environment specified, defaulting to: local
  set "ENV=local"
)

set "APP_NAME=bdf-chatbot"
set "CONTAINER_NAME=%APP_NAME%-%ENV%"
set "ENV_FILE=.env.%ENV%"
set "IMAGE_NAME=%APP_NAME%:%ENV%"
set "BUILDX_BUILDER=local_builder"
set "CACHE_DIR=%TEMP%\buildx-cache"

REM === Verify .env file exists ===
if not exist "%ENV_FILE%" (
  echo ❌ ERROR: Missing environment file: %ENV_FILE%
  exit /b 1
)

REM === Read NEXT_PUBLIC_API_BASE from env file ===
set "NEXT_PUBLIC_API_BASE="
for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
  if /I "%%A"=="NEXT_PUBLIC_API_BASE" set "NEXT_PUBLIC_API_BASE=%%B"
)
if "%NEXT_PUBLIC_API_BASE%"=="" (
  echo ❌ ERROR: NEXT_PUBLIC_API_BASE not found in %ENV_FILE%
  exit /b 1
)
echo 🌍 Using NEXT_PUBLIC_API_BASE=%NEXT_PUBLIC_API_BASE%

REM === Remove existing container if running ===
for /f %%i in ('docker ps -a --format "{{.Names}}"') do (
  if "%%i"=="%CONTAINER_NAME%" (
    echo 🗑 Removing existing container: %CONTAINER_NAME%
    docker rm -f %CONTAINER_NAME% >nul 2>&1
  )
)

REM === Ensure Buildx builder exists ===
docker buildx inspect %BUILDX_BUILDER% >nul 2>&1
if errorlevel 1 (
  echo 🔧 Creating local Buildx builder: %BUILDX_BUILDER%
  docker buildx create --name %BUILDX_BUILDER% --use
  docker buildx inspect --bootstrap
) else (
  echo ✅ Buildx builder '%BUILDX_BUILDER%' already exists.
)

REM === Prepare cache directory ===
if not exist "%CACHE_DIR%" (
  echo 📦 Creating cache directory: %CACHE_DIR%
  mkdir "%CACHE_DIR%" >nul 2>&1
)

REM === Enable BuildKit ===
set DOCKER_BUILDKIT=1

REM === Build image with persistent local cache ===
echo 🐳 Building Docker image with Buildx cache: %IMAGE_NAME%
docker buildx build ^
  --builder %BUILDX_BUILDER% ^
  --progress=plain ^
  --build-arg NEXT_PUBLIC_API_BASE=%NEXT_PUBLIC_API_BASE% ^
  --cache-from=type=local,src=%CACHE_DIR% ^
  --cache-to=type=local,dest=%CACHE_DIR%,mode=max ^
  -t %IMAGE_NAME% ^
  --load .

if errorlevel 1 (
  echo ❌ Docker build failed!
  exit /b 1
)

REM === Determine port mapping ===
if /I "%ENV%"=="stage" (
  set "PORT_MAPPING=80:80"
) else if /I "%ENV%"=="prod" (
  set "PORT_MAPPING=80:80"
) else (
  set "PORT_MAPPING=8080:80"
)

REM === Determine log driver ===
if /I "%ENV%"=="dev" (
  set "LOG_DRIVER=awslogs"
  set "LOG_OPTS=--log-driver=awslogs --log-opt awslogs-region=us-east-1 --log-opt awslogs-group=/bdf-chatbot/%ENV% --log-opt awslogs-stream=%CONTAINER_NAME%"
) else if /I "%ENV%"=="stage" (
  set "LOG_DRIVER=awslogs"
  set "LOG_OPTS=--log-driver=awslogs --log-opt awslogs-region=us-east-1 --log-opt awslogs-group=/bdf-chatbot/%ENV% --log-opt awslogs-stream=%CONTAINER_NAME%"
) else (
  set "LOG_DRIVER=json-file"
  set "LOG_OPTS=--log-driver=json-file"
)

echo 🐳 Using log driver: %LOG_DRIVER%

REM === Resource limits ===
set "MEMORY_LIMIT=7g"
set "CPU_LIMIT=2.0"

REM === Run container ===
echo 🚀 Running container: %CONTAINER_NAME%
docker run -d ^
  --env-file %ENV_FILE% ^
  %LOG_OPTS% ^
  -p %PORT_MAPPING% ^
  --memory %MEMORY_LIMIT% ^
  --cpus %CPU_LIMIT% ^
  --name %CONTAINER_NAME% ^
  %IMAGE_NAME%

if errorlevel 1 (
  echo ❌ Failed to start container!
  exit /b 1
)

REM === Display final info ===
for /f "tokens=1 delims=:" %%p in ("%PORT_MAPPING%") do set "EXPOSED_PORT=%%p"
echo ✅ Container running at: http://localhost:%EXPOSED_PORT%

if /I "%LOG_DRIVER%"=="json-file" (
  echo 📜 Use: docker logs -f %CONTAINER_NAME%
) else (
  echo 📜 Logs available in CloudWatch: /bdf-chatbot/%ENV%
)

REM === Show cache size ===
echo 📦 Build cache size:
for /f "tokens=1,*" %%a in ('powershell -NoProfile -Command "(Get-ChildItem -Recurse -Force \"%CACHE_DIR%\" | Measure-Object -Property Length -Sum).Sum /1MB"') do (
  echo     %%a MB in cache
)

endlocal
exit /b 0
