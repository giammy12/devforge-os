/* =============================================================================
 * DevForge OS — Compositor
 * shaders/shadow.glsl — Ombre morbide per le finestre
 *
 * Genera un'ombra "box shadow" con bordi sfumati per ogni finestra.
 * Parametri configurabili:
 *   - offset (X, Y): spostamento dell'ombra
 *   - blur_radius:   quanto l'ombra è morbida ai bordi
 *   - spread:        quanto l'ombra è più grande della finestra
 *   - color:         colore e opacità dell'ombra
 *
 * Valori usati da DevForge OS:
 *   offset=(0, 8px), blur=24px, spread=0, color=rgba(0,0,0,0.4)
 *
 * Il compositor disegna l'ombra PRIMA della finestra, nella posizione
 * calcolata: shadow_rect = window_rect espanso di spread, poi offset.
 * ============================================================================= */

/* ── Vertex Shader ───────────────────────────────────────────────────────── */
#ifdef VERTEX_SHADER

precision mediump float;

attribute vec2 a_position;
attribute vec2 a_texcoord;

varying vec2 v_texcoord;
varying vec2 v_pos;

void main() {
    v_texcoord  = a_texcoord;
    v_pos       = a_position;
    gl_Position = vec4(a_position, 0.0, 1.0);
}

#endif /* VERTEX_SHADER */

/* ── Fragment Shader ─────────────────────────────────────────────────────── */
#ifdef FRAGMENT_SHADER

precision mediump float;

uniform vec2  u_resolution;     /* dimensioni viewport in pixel */
uniform vec2  u_shadow_offset;  /* offset ombra in pixel (es. 0, 8) */
uniform float u_blur_radius;    /* raggio blur in pixel (es. 24.0) */
uniform float u_spread;         /* espansione ombra in pixel (es. 0.0) */
uniform vec4  u_shadow_color;   /* RGBA colore ombra (es. 0,0,0,0.4) */
uniform vec4  u_window_rect;    /* x, y, width, height della finestra in pixel */
uniform float u_corner_radius;  /* raggio angoli finestra in pixel */

varying vec2 v_texcoord;

/*
 * Calcola la distanza con segno da un rettangolo arrotondato.
 * Negativa = dentro il rettangolo, Positiva = fuori.
 */
float rounded_rect_sdf(vec2 point, vec2 half_size, float radius) {
    vec2 d = abs(point) - half_size + vec2(radius);
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - radius;
}

void main() {
    /* Posizione del pixel corrente in pixel-space */
    vec2 pixel = v_texcoord * u_resolution;

    /* Centro e metà dimensione della finestra (con spread) */
    vec2 window_center = vec2(
        u_window_rect.x + u_window_rect.z / 2.0,
        u_window_rect.y + u_window_rect.w / 2.0
    );
    vec2 half_size = vec2(
        u_window_rect.z / 2.0 + u_spread,
        u_window_rect.w / 2.0 + u_spread
    );

    /* Posizione del pixel relativa al centro dell'ombra (con offset) */
    vec2 shadow_pos = pixel - window_center - u_shadow_offset;

    /* Distanza dal rettangolo arrotondato dell'ombra */
    float dist = rounded_rect_sdf(shadow_pos, half_size, u_corner_radius);

    /* Sfuma il bordo in base al blur_radius.
     * smoothstep crea una transizione morbida tra pieno e trasparente. */
    float alpha = 1.0 - smoothstep(-u_blur_radius, u_blur_radius, dist);

    gl_FragColor = vec4(u_shadow_color.rgb, u_shadow_color.a * alpha);
}

#endif /* FRAGMENT_SHADER */
