package routers

import (
	"encoding/json"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"registro-comparativo/eagle/internal/handler"
	"registro-comparativo/eagle/internal/repository"
)

const origin = "http://127.0.0.1:8102"

type dimension struct {
	Method string `json:"metodo"`
	Route  string `json:"ruta"`
	Status int    `json:"estado"`
}

type measurement struct {
	dimension
	Total    int     `json:"total"`
	Duration float64 `json:"duracion_ms_suma"`
}

type observations struct {
	sync.Mutex
	requests map[dimension]measurement
	Errors   int            `json:"errores_total"`
	CORS     map[string]int `json:"cors"`
}

func New(store *repository.Store) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.RedirectTrailingSlash = false
	records := handler.Registros{Store: store}
	metrics := &observations{
		requests: make(map[dimension]measurement),
		CORS:     map[string]int{"options": 0, "permitidos": 0, "rechazados": 0},
	}
	router.Use(metrics.observe)
	router.Use(gin.CustomRecovery(func(c *gin.Context, _ any) {
		handler.Error(c, 500, "No se pudo procesar la solicitud.")
	}))
	router.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })
	router.POST("/registros", records.Register)
	router.GET("/registros/conteo", records.Count)
	router.GET("/imagenes/:nombre", records.Image)
	router.GET("/metrics", metrics.snapshot)
	router.NoRoute(func(c *gin.Context) { handler.Error(c, 404, "Ruta no encontrada.") })
	return router
}

func (m *observations) snapshot(c *gin.Context) {
	m.Lock()
	defer m.Unlock()
	items := make([]measurement, 0, len(m.requests))
	for _, item := range m.requests {
		items = append(items, item)
	}
	c.JSON(200, gin.H{"solicitudes": items, "errores_total": m.Errors, "cors": m.CORS})
}

func (m *observations) observe(c *gin.Context) {
	start := time.Now()
	req := c.Request
	received := c.GetHeader("Origin")
	_, hasOrigin := req.Header["Origin"]
	preflight := req.Method == "OPTIONS" && hasOrigin
	allowed := received == origin
	if preflight {
		method := c.GetHeader("Access-Control-Request-Method")
		allowed = allowed && (method == "GET" || method == "POST")
		for _, name := range strings.Split(c.GetHeader("Access-Control-Request-Headers"), ",") {
			switch strings.ToLower(strings.TrimSpace(name)) {
			case "", "content-type", "x-registro-cliente":
			default:
				allowed = false
			}
		}
	}

	c.Writer.Header().Add("Vary", "Origin")
	switch {
	case hasOrigin && !allowed:
		handler.Error(c, 403, "Origen CORS rechazado.")
	case preflight:
		c.Header("Access-Control-Allow-Origin", origin)
		c.Header("Access-Control-Allow-Methods", "GET, POST")
		c.Header("Access-Control-Allow-Headers", "Content-Type, X-Registro-Cliente")
		c.AbortWithStatus(204)
	default:
		if allowed {
			c.Header("Access-Control-Allow-Origin", origin)
		}
		c.Next()
	}
	path := req.URL.Path
	switch path {
	case "/health", "/registros", "/registros/conteo", "/metrics":
	default:
		path = "otra"
		if strings.HasPrefix(req.URL.Path, "/imagenes/") {
			path = "/imagenes/:nombre"
		}
	}
	status := c.Writer.Status()
	key := dimension{req.Method, path, status}
	m.Lock()
	entry := m.requests[key]
	entry.dimension = key
	entry.Total++
	entry.Duration += float64(time.Since(start)) / float64(time.Millisecond)
	m.requests[key] = entry
	if status >= 400 {
		m.Errors++
	}
	if req.Method == "OPTIONS" {
		m.CORS["options"]++
	}
	result := "rechazado"
	if hasOrigin {
		if allowed {
			result = "permitido"
			m.CORS["permitidos"]++
		} else {
			m.CORS["rechazados"]++
		}
	}
	m.Unlock()
	if hasOrigin {
		event, _ := json.Marshal(gin.H{"origen": received, "metodo": req.Method, "resultado": result, "estado": status})
		log.Printf("CORS %s", event)
	}
}
