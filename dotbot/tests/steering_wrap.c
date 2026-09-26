/* Host build of DotBot-libs drv/steering with the sandbox dotbot app's conf,
 * flattened for ctypes: dotbot/tests/test_steering_fidelity.py builds it. */
#include <math.h>
#include <string.h>

#include "geometry.h"
#include "steering.h"

static db_steering_conf_t _conf = {
    .lever_mm              = DB_LH2_LEVER_ARM_EFFECTIVE,
    .v_max_mm_s            = DB_STEERING_V_MAX_MM_S,
    .approach_per_s        = DB_STEERING_APPROACH_PER_S,
    .runon_s               = DB_STEERING_RUNON_S,
    .spin_mm_s             = DB_STEERING_SPIN_MM_S,
    .spin_min_mm_s         = DB_STEERING_SPIN_MIN_MM_S,
    .heading_kp            = DB_STEERING_HEADING_KP,
    .heading_kd            = DB_STEERING_HEADING_KD,
    .align_enter_deg       = DB_STEERING_ALIGN_ENTER_DEG,
    .align_exit_deg        = DB_STEERING_ALIGN_EXIT_DEG,
    .full_speed_deg        = DB_STEERING_FULL_SPEED_DEG,
    .final_tol_deg         = DB_STEERING_FINAL_TOL_DEG,
    .near_mm               = DB_STEERING_NEAR_MM,
    .bearing_min_mm        = DB_STEERING_BEARING_MIN_MM,
    .lookahead_s           = DB_STEERING_LOOKAHEAD_S,
    .arrival_min_mm        = DB_STEERING_ARRIVAL_MIN_MM,
    .precise_min_mm        = DB_STEERING_PRECISE_MIN_MM,
    .pass_mm               = DB_STEERING_PASS_MM,
    .creep_mm_s            = DB_STEERING_CREEP_MM_S,
    .settle_skip_ticks     = DB_STEERING_SETTLE_SKIP_TICKS,
    .settle_fixes          = DB_STEERING_SETTLE_FIXES,
    .settle_ticks          = DB_STEERING_SETTLE_TICKS,
    .settle_nudges         = DB_STEERING_SETTLE_NUDGES,
    .nudge_ticks           = DB_STEERING_NUDGE_TICKS,
    .no_heading_turn_ticks = DB_STEERING_NO_HEADING_TURN_TICKS,
    .no_heading_ticks      = DB_STEERING_NO_HEADING_TICKS,
    .turn_ticks            = DB_STEERING_TURN_TICKS,
    .progress_ticks        = DB_STEERING_PROGRESS_TICKS,
    .progress_mm           = DB_STEERING_PROGRESS_MM,
    .hold_ticks            = DB_STEERING_HOLD_TICKS,
    .recover               = DB_STEERING_RECOVER_DRIVE,
    .recover_mm            = DB_STEERING_RECOVER_MM,
    .recover_mm_s          = DB_STEERING_RECOVER_MM_S,
    .bounds_mm             = { 0, 0, 10000.0f, 10000.0f },
    .bounds_margin_mm      = DB_STEERING_BOUNDS_MARGIN_MM,
};

static db_steering_t _steering;

/* The conf the app builds, for checking the Python defaults against:
 * v_max, approach, runon, spin, spin_min, kp, kd, align_enter, align_exit,
 * full_speed, final_tol, near, bearing_min, lookahead, arrival_min,
 * precise_min, pass, creep, progress_mm, recover_mm, recover_mm_s,
 * bounds_margin, lever, then the tick counts as floats: settle_skip,
 * settle_fixes, settle_ticks, settle_nudges, nudge_ticks,
 * no_heading_turn_ticks, no_heading_ticks, turn_ticks, progress_ticks,
 * hold_ticks, and the effective tracks: spin, arc, arc ratio */
int w_conf(float *o) {
    const db_steering_conf_t *c = &_conf;
    float v[] = {
        c->v_max_mm_s, c->approach_per_s, c->runon_s, c->spin_mm_s, c->spin_min_mm_s,
        c->heading_kp, c->heading_kd, c->align_enter_deg, c->align_exit_deg,
        c->full_speed_deg, c->final_tol_deg, c->near_mm, c->bearing_min_mm,
        c->lookahead_s, c->arrival_min_mm, c->precise_min_mm, c->pass_mm,
        c->creep_mm_s, c->progress_mm, c->recover_mm, c->recover_mm_s,
        c->bounds_margin_mm, c->lever_mm,
        (float)c->settle_skip_ticks, (float)c->settle_fixes, (float)c->settle_ticks,
        (float)c->settle_nudges, (float)c->nudge_ticks, (float)c->no_heading_turn_ticks,
        (float)c->no_heading_ticks, (float)c->turn_ticks, (float)c->progress_ticks,
        (float)c->hold_ticks, DB_TRACK_EFFECTIVE, DB_TRACK_EFFECTIVE_ARC,
        DB_TRACK_EFFECTIVE_ARC_RATIO,
    };
    memcpy(o, v, sizeof(v));
    return (int)(sizeof(v) / sizeof(v[0]));
}

void w_init(void) {
    db_steering_init(&_steering, &_conf);
}

/* xy: count pairs; headings: count values, NAN for none */
void w_set_path(int count, const float *xy, const float *headings, float threshold, float pass_mm, float tol) {
    db_steering_path_t path = { 0 };
    path.count              = (uint8_t)count;
    path.threshold_mm       = threshold;
    path.pass_mm            = pass_mm;
    path.heading_tol_deg    = tol;
    for (int i = 0; i < count && i < (int)DB_STEERING_MAX_POINTS; i++) {
        path.points[i].x_mm        = xy[2 * i];
        path.points[i].y_mm        = xy[2 * i + 1];
        path.points[i].has_heading = !isnan(headings[i]);
        path.points[i].heading_deg = isnan(headings[i]) ? 0 : headings[i];
    }
    db_steering_set_path(&_steering, &path);
}

static void _pose(db_steering_pose_t *pose, int status, float x, float y, float h) {
    pose->status      = (db_steering_pose_status_t)status;
    pose->x_mm        = x;
    pose->y_mm        = y;
    pose->heading_deg = h;
}

/* out: left, right, brake */
void w_step(int status, float x, float y, float h, unsigned elapsed, float *out) {
    db_steering_pose_t   pose;
    db_steering_output_t o;
    _pose(&pose, status, x, y, h);
    db_steering_step(&_steering, &pose, elapsed, &o);
    out[0] = o.left_mm_s;
    out[1] = o.right_mm_s;
    out[2] = o.brake ? 1.0f : 0.0f;
}

int w_poll(int status, float x, float y, float h, float *out) {
    db_steering_pose_t   pose;
    db_steering_output_t o;
    _pose(&pose, status, x, y, h);
    if (!db_steering_poll(&_steering, &pose, &o)) {
        return 0;
    }
    out[0] = o.left_mm_s;
    out[1] = o.right_mm_s;
    out[2] = o.brake ? 1.0f : 0.0f;
    return 1;
}

void w_fix(float x, float y) {
    db_steering_fix(&_steering, x, y);
}

void w_stop(void) {
    db_steering_stop(&_steering);
}

void w_set_max_speed(float v) {
    db_steering_set_max_speed(&_steering, v);
}

/* state, completion, fail, index, active */
void w_get(int *o, float *f) {
    o[0] = (int)_steering.state;
    o[1] = (int)_steering.completion;
    o[2] = (int)_steering.fail;
    o[3] = (int)_steering.index;
    o[4] = db_steering_active(&_steering) ? 1 : 0;
    f[0] = _steering.target.x_mm;
    f[1] = _steering.target.y_mm;
    f[2] = _steering.v_max_mm_s;
}
