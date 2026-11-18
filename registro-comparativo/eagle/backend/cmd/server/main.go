package main

import (
	"context"
	"log"
	"net"
	"os"
	"time"

	eaglehttp "github.com/go-eagle/eagle/pkg/transport/http"

	"registro-comparativo/eagle/internal/repository"
	"registro-comparativo/eagle/internal/routers"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	data := os.Getenv("REGISTRO_DATA_DIR")
	if data == "" {
		data = "data"
	}
	store, err := repository.Open(data)
	if err != nil {
		log.Fatal(err)
	}
	defer store.Close()

	server := eaglehttp.NewServer(
		eaglehttp.WithAddress(net.JoinHostPort("127.0.0.1", port)),
		eaglehttp.WithReadTimeout(30*time.Second),
		eaglehttp.WithWriteTimeout(30*time.Second),
	)
	// Install the Gin router as the embedded HTTP handler. Eagle v1.11.0's
	// default ServeHTTP delegates to itself if the handler is left unchanged.
	server.Server.Handler = routers.New(store)
	if err := server.Start(context.Background()); err != nil {
		log.Fatal(err)
	}
}
