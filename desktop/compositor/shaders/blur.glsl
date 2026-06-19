/* =============================================================================
 * DevForge OS — Compositor
 * shaders/blur.glsl — Gaussian blur a due passate per il glassmorphism
 *
 * Implementa un blur gaussiano separabile:
 *   Passata 1 (orizzontale): campiona pixel lungo l'asse X con peso gaussiano
 *   Passata 2 (verticale):   campiona pixel lungo l'asse Y con peso gaussiano
 * Risultato: blur morbido con complessità O(N) invece di O(N²).
 *
 * Questo shader viene caricato dal compositor e applicato alla texture
 * dello sfondo PRIMA di renderizzare la finestra semitrasparente sopra,
 * creando l'effetto vetro smerigliato (glassmorphism).
 *
 * Dipendenze: OpenGL ES 2.0 (supportato da wlroots su Debian 12)
 * ============================================================================= */

/* ── Vertex Shader ───────────────────────────────────────────────────────── */
#ifdef VERTEX_SHADER

precision mediump float;

attribute vec2 a_position;   /* coordinate clip-space [-1, 1] */
attribute vec2 a_texcoord;   /* coordinate texture [0, 1]     */

varying vec2 v_texcoord;

void main() {
    v_texcoord  = a_texcoord;
    gl_Position = vec4(a_position, 0.0, 1.0);
}

#endif /* VERTEX_SHADER */

/* ── Fragment Shader ─────────────────────────────────────────────────────── */
#ifdef FRAGMENT_SHADER

precision mediump float;

uniform sampler2D u_texture;     /* texture dello sfondo da sfuocare */
uniform vec2      u_resolution;  /* dimensioni del viewport in pixel */
uniform bool      u_horizontal;  /* true = passata orizzontale, false = verticale */
uniform float     u_radius;      /* raggio blur in pixel (default: 12.0)  */

varying vec2 v_texcoord;

/*
 * Pesi gaussiani precomputati per kernel 15-tap (raggio = 7).
 * Formula: w(i) = exp(-i²/(2σ²)) con σ = radius/2.5
 * Normalizzati in modo che la somma = 1.
 */
const float WEIGHTS[8] = float[8](
    0.2270270270,  /* centro  */
    0.1945945946,  /* ±1 px   */
    0.1216216216,  /* ±2 px   */
    0.0540540541,  /* ±3 px   */
    0.0162162162,  /* ±4 px   */
    0.0054054054,  /* ±5 px   */
    0.0016216216,  /* ±6 px   */
    0.0005405405   /* ±7 px   */
);

void main() {
    vec2 tex_offset = 1.0 / u_resolution;  /* dimensione di un pixel in UV */
    vec4 result = texture2D(u_texture, v_texcoord) * WEIGHTS[0];

    if (u_horizontal) {
        /* Passata orizzontale: campiona sinistra e destra */
        for (int i = 1; i < 8; i++) {
            float offset = float(i) * tex_offset.x * u_radius;
            result += texture2D(u_texture, v_texcoord + vec2(offset, 0.0))
                      * WEIGHTS[i];
            result += texture2D(u_texture, v_texcoord - vec2(offset, 0.0))
                      * WEIGHTS[i];
        }
    } else {
        /* Passata verticale: campiona sopra e sotto */
        for (int i = 1; i < 8; i++) {
            float offset = float(i) * tex_offset.y * u_radius;
            result += texture2D(u_texture, v_texcoord + vec2(0.0, offset))
                      * WEIGHTS[i];
            result += texture2D(u_texture, v_texcoord - vec2(0.0, offset))
                      * WEIGHTS[i];
        }
    }

    gl_FragColor = result;
}

#endif /* FRAGMENT_SHADER */
