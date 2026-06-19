/* =============================================================================
 * DevForge OS — Compositor
 * shaders/transition.glsl — Transizioni tra workspace
 *
 * Supporta 3 tipi di transizione:
 *   0 = SLIDE:  le due texture scivolano orizzontalmente
 *   1 = FADE:   crossfade tra le due texture
 *   2 = ZOOM:   la texture uscente si rimpicciolisce, quella entrante cresce
 *
 * DevForge OS usa SLIDE (tipo 0) per le transizioni workspace.
 *
 * Parametri:
 *   u_from:     texture workspace corrente (uscente)
 *   u_to:       texture workspace target (entrante)
 *   u_progress: avanzamento animazione [0.0, 1.0]
 *   u_direction: 1.0 = destra→sinistra, -1.0 = sinistra→destra
 *   u_type:     tipo transizione (0=slide, 1=fade, 2=zoom)
 * ============================================================================= */

/* ── Vertex Shader ───────────────────────────────────────────────────────── */
#ifdef VERTEX_SHADER

precision mediump float;

attribute vec2 a_position;
attribute vec2 a_texcoord;

varying vec2 v_texcoord;

void main() {
    v_texcoord  = a_texcoord;
    gl_Position = vec4(a_position, 0.0, 1.0);
}

#endif /* VERTEX_SHADER */

/* ── Fragment Shader ─────────────────────────────────────────────────────── */
#ifdef FRAGMENT_SHADER

precision mediump float;

uniform sampler2D u_from;       /* workspace uscente */
uniform sampler2D u_to;         /* workspace entrante */
uniform float     u_progress;   /* 0.0 = inizio, 1.0 = fine */
uniform float     u_direction;  /* 1.0 = →, -1.0 = ← */
uniform int       u_type;       /* 0=slide, 1=fade, 2=zoom */

varying vec2 v_texcoord;

/* ── Easing ease-in-out cubic ────────────────────────────────────────────── */
float ease_in_out(float t) {
    return t < 0.5
        ? 4.0 * t * t * t
        : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0;
}

/* ── Slide transition ────────────────────────────────────────────────────── */
vec4 slide(vec2 uv) {
    float p = ease_in_out(u_progress);
    float offset = p * u_direction;

    /* UV del workspace uscente: si sposta a sinistra/destra */
    vec2 uv_from = uv + vec2(offset, 0.0);
    /* UV del workspace entrante: arriva dall'altro lato */
    vec2 uv_to   = uv + vec2(offset - u_direction, 0.0);

    /* Campiona la texture corretta in base a quale workspace è visibile */
    if (uv.x * u_direction + p * u_direction > u_direction) {
        /* Zona del workspace entrante */
        if (uv_to.x >= 0.0 && uv_to.x <= 1.0) {
            return texture2D(u_to, uv_to);
        }
    }
    if (uv_from.x >= 0.0 && uv_from.x <= 1.0) {
        return texture2D(u_from, uv_from);
    }
    return vec4(0.0, 0.0, 0.0, 1.0);
}

/* ── Fade (crossfade) transition ─────────────────────────────────────────── */
vec4 fade_transition(vec2 uv) {
    float p = ease_in_out(u_progress);
    vec4 c_from = texture2D(u_from, uv);
    vec4 c_to   = texture2D(u_to,   uv);
    return mix(c_from, c_to, p);
}

/* ── Zoom transition ─────────────────────────────────────────────────────── */
vec4 zoom_transition(vec2 uv) {
    float p = ease_in_out(u_progress);

    /* Workspace uscente: rimpicciolisce verso il centro */
    float scale_from = 1.0 - p * 0.1;
    vec2 uv_from = (uv - 0.5) / scale_from + 0.5;

    /* Workspace entrante: cresce da 0.9 a 1.0 */
    float scale_to = 0.9 + p * 0.1;
    vec2 uv_to   = (uv - 0.5) / scale_to + 0.5;

    vec4 c_from = (uv_from.x >= 0.0 && uv_from.x <= 1.0 &&
                   uv_from.y >= 0.0 && uv_from.y <= 1.0)
        ? texture2D(u_from, uv_from) * (1.0 - p)
        : vec4(0.0);

    vec4 c_to = (uv_to.x >= 0.0 && uv_to.x <= 1.0 &&
                 uv_to.y >= 0.0 && uv_to.y <= 1.0)
        ? texture2D(u_to, uv_to) * p
        : vec4(0.0);

    return c_from + c_to;
}

void main() {
    if (u_type == 1) {
        gl_FragColor = fade_transition(v_texcoord);
    } else if (u_type == 2) {
        gl_FragColor = zoom_transition(v_texcoord);
    } else {
        gl_FragColor = slide(v_texcoord);
    }
}

#endif /* FRAGMENT_SHADER */
