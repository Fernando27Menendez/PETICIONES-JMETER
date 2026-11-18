package repository

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
	sqlite "modernc.org/sqlite"
)

var ErrDuplicate = errors.New("DNI duplicado")

type Store struct {
	db     *sql.DB
	Images string
}

func Open(data string) (*Store, error) {
	images := filepath.Join(data, "imagenes")
	if err := os.MkdirAll(images, 0755); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", filepath.Join(data, "registros.sqlite3"))
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	_, err = db.Exec(`
		PRAGMA journal_mode=WAL;
		PRAGMA busy_timeout=5000;
		CREATE TABLE IF NOT EXISTS registros (
			id INTEGER PRIMARY KEY, dni TEXT NOT NULL UNIQUE,
			nombres TEXT NOT NULL, apellidos TEXT NOT NULL, imagen TEXT NOT NULL UNIQUE
		);
	`)
	if err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db, Images: images}, nil
}

func (s *Store) Close() error { return s.db.Close() }

func (s *Store) Count(ctx context.Context) (int, error) {
	var total int
	err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM registros").Scan(&total)
	return total, err
}

type Registro struct {
	ID        int64  `json:"id"`
	DNI       string `json:"dni"`
	Nombres   string `json:"nombres"`
	Apellidos string `json:"apellidos"`
	Imagen    string `json:"imagen"`
}

func (s *Store) Save(ctx context.Context, dni, names, surnames, extension string, payload []byte) (Registro, error) {
	filename := strings.ReplaceAll(uuid.NewString(), "-", "") + "." + extension
	row := Registro{DNI: dni, Nombres: names, Apellidos: surnames, Imagen: "/imagenes/" + filename}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return row, err
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, "INSERT INTO registros(dni,nombres,apellidos,imagen) VALUES(?,?,?,?)",
		dni, names, surnames, filename)
	if err != nil {
		var constraint *sqlite.Error
		if errors.As(err, &constraint) && constraint.Code() == 2067 && strings.Contains(err.Error(), "registros.dni") {
			return row, ErrDuplicate
		}
		return row, err
	}
	row.ID, err = result.LastInsertId()
	if err != nil {
		return row, err
	}

	path := filepath.Join(s.Images, filename)
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return row, err
	}
	_, writeErr := file.Write(payload)
	err = errors.Join(writeErr, file.Close())
	if err == nil {
		err = tx.Commit()
	}
	if err != nil {
		return row, errors.Join(err, os.Remove(path))
	}
	return row, nil
}
