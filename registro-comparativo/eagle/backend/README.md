# Eagle

Desde `eagle/backend`, con Go 1.23 o posterior.

```powershell
go build -o bin/eagle.exe ./cmd/server
.\bin\eagle.exe
```

El proceso usa `github.com/go-eagle/eagle/pkg/transport/http` v1.11.0 para construir e iniciar el servidor, con Gin como manejador del `http.Server` embebido. La asignación explícita del manejador evita la autorreferencia del `ServeHTTP` predeterminado de esa versión. La estructura conserva `cmd/server`, `internal/routers`, `internal/handler` e `internal/repository` del esquema de Eagle. El handler usa multipart y decodificadores PNG/JPEG de Go. El repositorio usa SQLite mediante `modernc.org/sqlite` sin CGO. La conexión única serializa las escrituras SQLite. La aplicación funciona sin Redis, MySQL ni gRPC. El transporte oficial trae dependencias transitivas que resuelve Go Modules, sin requerir procesos adicionales.

`PORT` ajusta el puerto (8080 por defecto). `REGISTRO_DATA_DIR` ajusta la carpeta de datos (`data` en el directorio de trabajo por defecto).
