package handler

import (
	"bytes"
	"errors"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/gin-gonic/gin"
	"registro-comparativo/eagle/internal/repository"
)

const limit = 1_000_000

var dniPattern = regexp.MustCompile(`^[0-9]{8}$`)
var imagePattern = regexp.MustCompile(`^[a-f0-9]{32}\.(png|jpg)$`)

type Registros struct{ Store *repository.Store }

func Error(c *gin.Context, status int, message string) {
	c.AbortWithStatusJSON(status, gin.H{"error": message})
}

func (h Registros) Count(c *gin.Context) {
	total, err := h.Store.Count(c.Request.Context())
	if err != nil {
		log.Print(err)
		Error(c, 500, "No se pudo procesar la solicitud.")
		return
	}
	c.JSON(200, gin.H{"total": total})
}

func (h Registros) Image(c *gin.Context) {
	filename := c.Param("nombre")
	if !imagePattern.MatchString(filename) {
		Error(c, 404, "Imagen no encontrada.")
		return
	}
	path := filepath.Join(h.Store.Images, filename)
	if info, err := os.Stat(path); err != nil || !info.Mode().IsRegular() {
		Error(c, 404, "Imagen no encontrada.")
		return
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.File(path)
}

func (h Registros) Register(c *gin.Context) {
	req := c.Request
	contentType, _, _ := mime.ParseMediaType(req.Header.Get("Content-Type"))
	if contentType != "multipart/form-data" {
		Error(c, 400, "Se requiere multipart/form-data.")
		return
	}
	req.Body = http.MaxBytesReader(c.Writer, req.Body, 5*limit)
	if err := req.ParseMultipartForm(limit); err != nil {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			Error(c, 413, "La imagen debe pesar menos de 1 000 000 bytes.")
		} else {
			Error(c, 400, "Formulario multipart inválido.")
		}
		return
	}
	defer req.MultipartForm.RemoveAll()
	fields := req.MultipartForm.Value
	files := req.MultipartForm.File
	dni := req.PostFormValue("dni")
	names := strings.TrimSpace(req.PostFormValue("nombres"))
	surnames := strings.TrimSpace(req.PostFormValue("apellidos"))
	switch {
	case len(fields) > 3 || len(fields["dni"]) > 1 || len(fields["nombres"]) > 1 || len(fields["apellidos"]) > 1 ||
		len(files) > 1 || len(files["imagen"]) > 1:
		Error(c, 400, "Formulario multipart inválido.")
	case !dniPattern.MatchString(dni):
		Error(c, 400, "El DNI debe tener exactamente ocho dígitos.")
	case names == "":
		Error(c, 400, "Los nombres son obligatorios.")
	case surnames == "":
		Error(c, 400, "Los apellidos son obligatorios.")
	case len(files["imagen"]) == 0:
		Error(c, 400, "La imagen es obligatoria.")
	default:
		h.save(c, dni, names, surnames)
	}
}

func (h Registros) save(c *gin.Context, dni, names, surnames string) {
	file, _, err := c.Request.FormFile("imagen")
	if err != nil {
		Error(c, 400, "Formulario multipart inválido.")
		return
	}
	defer file.Close()
	payload, err := io.ReadAll(io.LimitReader(file, limit))
	if err != nil {
		Error(c, 400, "Formulario multipart inválido.")
		return
	}
	if len(payload) >= limit {
		Error(c, 413, "La imagen debe pesar menos de 1 000 000 bytes.")
		return
	}
	_, format, err := image.Decode(bytes.NewReader(payload))
	if err != nil || (format != "png" && format != "jpeg") {
		Error(c, 415, "La imagen debe ser un PNG o JPEG válido.")
		return
	}
	extension := "png"
	if format == "jpeg" {
		extension = "jpg"
	}
	row, err := h.Store.Save(c.Request.Context(), dni, names, surnames, extension, payload)
	if errors.Is(err, repository.ErrDuplicate) {
		Error(c, 409, "El DNI ya está registrado.")
		return
	}
	if err != nil {
		log.Print(err)
		Error(c, 500, "No se pudo procesar la solicitud.")
		return
	}
	c.JSON(201, row)
}
