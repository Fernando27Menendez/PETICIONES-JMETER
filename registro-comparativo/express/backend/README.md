# Express

Desde `express/backend`, con Node.js 24 y las dependencias instaladas según el README principal.

```powershell
npm.cmd start
```

El puerto predeterminado es 3000 y puede ajustarse con `PORT`. Express usa el servidor HTTP de Node, Multer para multipart en memoria, Sharp para decodificación y `node:sqlite` para guardar la fila. La transacción y la escritura del archivo son síncronas. `REGISTRO_DATA_DIR` puede indicar un directorio de datos alternativo. El valor predeterminado es `express/backend/data`.
