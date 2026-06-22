# eactgen — generador de eActivity para CASIO

Genera archivos **eActivity** de CASIO (`.g2e` / `.g1e`) para las calculadoras gráficas
de la serie fx-9860G directamente en tu computadora: escribe tus fórmulas en texto plano
con un pequeño marcado tipo LaTeX y obtén un archivo listo para pasar a la calculadora.

Es una recreación local e independiente de la herramienta en línea
[EactMaker](https://tools.planet-casio.com/EactMaker/): el formato binario de las
eActivity se obtuvo por ingeniería inversa a partir de archivos reales de EactMaker, y
el generador reproduce esa salida **byte por byte** (11/11 archivos de ejemplo, 61/61
líneas de contenido verificadas).

Sin dependencias: solo Python 3 y la tabla de caracteres incluida `chars.toml`
(del proyecto [Cahute](https://cahute.org), licencia CeCILL 2.1).

## Por qué

La calculadora no guarda el texto como Unicode; usa la codificación propia de CASIO
*FONTCHARACTER* (nabla, letras griegas, superíndices, fracciones, integrales…).
Escribir eso en el dispositivo es tedioso. Esta herramienta te permite redactar con un
teclado de verdad y produce un archivo válido que la calculadora abre.

> **Extensiones.** La fx-9860G**III** abre **tanto `.g1e` como `.g2e`**: los dos
> contenedores son idénticos byte a byte; solo cambia la extensión (`.g2e` es el formato
> nativo de la GII/GIII, `.g1e` es el de la fx-9860G antigua). `.g2e` es el valor por
> defecto seguro. Si un archivo no abre, la causa es el *contenido*, no la extensión.

## Instalación

```bash
git clone <url-del-repo> eactgen && cd eactgen
# Python 3, sin paquetes adicionales
```

## Uso

Escribe una línea de la eActivity por renglón en un archivo de texto UTF-8 (`notas.txt`):

```
∇²V=0
E=-∇V
We=½CV²=\int{}{x=V}{½εE²}dV
\int{}{C}{E·dl}=0
J=[A/m²]
ρ_v=\frac{Q_e}{ε₀}
```

Genera el archivo:

```bash
python3 casio_translate.py build notas.txt --title PHYS -o PHYS.g2e
```

- `--title` (≤8 caracteres) se convierte en el encabezado `======PHYS======` que aparece
  como primera línea.
- El **nombre en la calculadora viene del nombre del archivo de salida** (`PHYS.g2e` →
  "PHYS", ≤8 caracteres, en mayúsculas). *No* se guarda dentro del archivo.

Luego copia `PHYS.g2e` a la calculadora (almacenamiento USB / Link / FA-124) y ábrelo
desde el menú eActivity.

### Otros comandos

```bash
python3 casio_translate.py encode "∇²V=0"               # muestra los bytes CASIO (hex)
python3 casio_translate.py decode-hex "d8 a8 1a 32 1b"  # bytes -> texto legible
python3 casio_translate.py inspect FILE.g2e             # verifica encabezado + texto
```

## Marcado

| Escribes | Resultado |
|----------|-----------|
| `\frac{a}{b}` | fracción apilada |
| `½ ⅓ ¼ …` | fracción apilada (glifos de fracción) |
| `\sqrt{x}` | raíz cuadrada |
| `\abs{x}` | valor absoluto / módulo |
| `\int{inf}{sup}{f}` | integral (cualquier argumento puede ir vacío: `\int{}{x=V}{f}`) |
| `\log{a}{b}` | logaritmo en base *a* de *b* |
| `\sum{n}{k}{0}{a}` | sumatoria (cantidad, variable, inicio, expresión) |
| `\mat{a&b}{c&d}` | matriz (filas en `{}`, celdas separadas por `&`) |
| `\diff{a}{b}` / `\diff2{a}{b}` | derivada 1ª / 2ª de *a* respecto de *b* |
| `\note{título}{cuerpo}` | nota / recuadro (en su propia línea) |
| `^2`, `^{n+1}` | superíndice / potencia |
| `_v`, `_{12}` | subíndice (letras y dígitos) |
| `²` `³` | glifos de superíndice |
| `∇ ∂ · ⇒ ε μ π σ ρ θ Ω …` | se escriben directamente como Unicode |
| `\nabla \partial \epsilon \pi \sigma …` | nombres LaTeX, si son más cómodos de teclear |

El ASCII normal pasa sin cambios. Coincide exactamente con el marcado de EactMaker: cada
archivo de ejemplo se regenera byte por byte.

## Limitaciones

- Una nota con cuerpo vacío (`\note{T}{}`) es degenerada en EactMaker: dale cuerpo a las notas.
- Verificado en `.g2e`/`.g1e` de la familia fx-9860G. El formato `.g3e` de la fx-CG
  (Prizm) *no* está contemplado.

## Cómo funciona

Consulta [`AGENTS.md`](AGENTS.md) para el formato completo obtenido por ingeniería
inversa: encabezado estándar y sumas de control, el directorio MCS, la disposición de
las celdas y el mapeo completo de marcado→bytes. La implementación es un solo archivo,
`casio_translate.py`.

## Créditos

- Tabla de caracteres: proyecto [Cahute](https://cahute.org) (Thomas Touhey), CeCILL 2.1.
- Formato inspirado en / verificado contra [EactMaker](https://tools.planet-casio.com/EactMaker/)
  de Helder7 y Ziqumu, y el trabajo de ingeniería inversa de SimonLothar.

## Aviso

CASIO y fx-9860G son marcas registradas de CASIO Computer Co., Ltd. Esta es una
herramienta independiente y no oficial. Haz copias de seguridad de los archivos de tu
calculadora.
