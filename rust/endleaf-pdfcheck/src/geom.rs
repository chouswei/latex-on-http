//! Own geometry in place of shapely/GEOS and scipy: convex clipping, line clipping
//! (Liang–Barsky / Cyrus–Beck), point-in-polygon, areas, a box grid and a kd-tree kNN.

pub type P = [f64; 2];

#[inline]
pub fn cross(o: P, a: P, b: P) -> f64 {
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
}

/// Signed shoelace area of a ring (closing point optional).
pub fn signed_area(ring: &[P]) -> f64 {
    let n = ring.len();
    if n < 3 {
        return 0.0;
    }
    let mut s = 0.0;
    for i in 0..n {
        let a = ring[i];
        let b = ring[(i + 1) % n];
        s += a[0] * b[1] - b[0] * a[1];
    }
    s / 2.0
}

pub fn area(ring: &[P]) -> f64 {
    signed_area(ring).abs()
}

pub fn bounds(pts: &[P]) -> [f64; 4] {
    let mut b = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    for p in pts {
        b[0] = b[0].min(p[0]);
        b[1] = b[1].min(p[1]);
        b[2] = b[2].max(p[0]);
        b[3] = b[3].max(p[1]);
    }
    b
}

/// Drop a repeated closing point.
pub fn open_ring(ring: &[P]) -> &[P] {
    if ring.len() > 1 && ring[0] == ring[ring.len() - 1] {
        &ring[..ring.len() - 1]
    } else {
        ring
    }
}

/// Sutherland–Hodgman: `subject` (any simple polygon) clipped by the convex `clip`.
pub fn clip_convex(subject: &[P], clip: &[P]) -> Vec<P> {
    let clip = open_ring(clip);
    let mut out: Vec<P> = open_ring(subject).to_vec();
    if clip.len() < 3 {
        return vec![];
    }
    let orient = if signed_area(clip) >= 0.0 { 1.0 } else { -1.0 };
    for i in 0..clip.len() {
        if out.is_empty() {
            break;
        }
        let a = clip[i];
        let b = clip[(i + 1) % clip.len()];
        let input = std::mem::take(&mut out);
        let inside = |p: P| orient * cross(a, b, p) >= 0.0;
        for j in 0..input.len() {
            let cur = input[j];
            let prev = input[(j + input.len() - 1) % input.len()];
            let (ci, pi) = (inside(cur), inside(prev));
            if ci {
                if !pi {
                    if let Some(x) = line_x(prev, cur, a, b) {
                        out.push(x);
                    }
                }
                out.push(cur);
            } else if pi {
                if let Some(x) = line_x(prev, cur, a, b) {
                    out.push(x);
                }
            }
        }
    }
    out
}

/// Intersection of segment p-q with the infinite line a-b.
fn line_x(p: P, q: P, a: P, b: P) -> Option<P> {
    let d1 = [q[0] - p[0], q[1] - p[1]];
    let d2 = [b[0] - a[0], b[1] - a[1]];
    let den = d1[0] * d2[1] - d1[1] * d2[0];
    if den == 0.0 {
        return None;
    }
    let t = ((a[0] - p[0]) * d2[1] - (a[1] - p[1]) * d2[0]) / den;
    Some([p[0] + t * d1[0], p[1] + t * d1[1]])
}

/// Liang–Barsky clip of segment p-q to the closed box [x0,y0,x1,y1]: parameter range.
pub fn liang_barsky(p: P, q: P, b: [f64; 4]) -> Option<(f64, f64)> {
    let d = [q[0] - p[0], q[1] - p[1]];
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    let checks = [
        (-d[0], p[0] - b[0]),
        (d[0], b[2] - p[0]),
        (-d[1], p[1] - b[1]),
        (d[1], b[3] - p[1]),
    ];
    for (pp, qq) in checks {
        if pp == 0.0 {
            if qq < 0.0 {
                return None;
            }
        } else {
            let r = qq / pp;
            if pp < 0.0 {
                t0 = t0.max(r);
            } else {
                t1 = t1.min(r);
            }
        }
    }
    if t0 > t1 {
        None
    } else {
        Some((t0, t1))
    }
}

/// Cyrus–Beck (Liang–Barsky generalised to a convex polygon, boundary inclusive).
pub fn clip_segment_convex(p: P, q: P, poly: &[P]) -> Option<(f64, f64)> {
    let poly = open_ring(poly);
    let n = poly.len();
    if n < 3 {
        return None;
    }
    let orient = if signed_area(poly) >= 0.0 { 1.0 } else { -1.0 };
    let d = [q[0] - p[0], q[1] - p[1]];
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    for i in 0..n {
        let a = poly[i];
        let b = poly[(i + 1) % n];
        // inside: orient * cross(a, b, x) >= 0; along the segment f(t) = num + t * den
        let num = orient * cross(a, b, p);
        let den = orient * ((b[0] - a[0]) * d[1] - (b[1] - a[1]) * d[0]);
        if den == 0.0 {
            if num < 0.0 {
                return None;
            }
        } else {
            let t = -num / den;
            if den > 0.0 {
                t0 = t0.max(t);
            } else {
                t1 = t1.min(t);
            }
        }
    }
    if t0 > t1 {
        None
    } else {
        Some((t0, t1))
    }
}

pub fn seg_intersect(p1: P, p2: P, q1: P, q2: P) -> bool {
    let d1 = cross(q1, q2, p1);
    let d2 = cross(q1, q2, p2);
    let d3 = cross(p1, p2, q1);
    let d4 = cross(p1, p2, q2);
    if ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    {
        return true;
    }
    let on = |a: P, b: P, c: P| {
        c[0] >= a[0].min(b[0])
            && c[0] <= a[0].max(b[0])
            && c[1] >= a[1].min(b[1])
            && c[1] <= a[1].max(b[1])
    };
    (d1 == 0.0 && on(q1, q2, p1))
        || (d2 == 0.0 && on(q1, q2, p2))
        || (d3 == 0.0 && on(p1, p2, q1))
        || (d4 == 0.0 && on(p1, p2, q2))
}

/// Segment-segment intersection point (proper or touching), if any.
pub fn seg_point(p1: P, p2: P, q1: P, q2: P) -> Option<P> {
    if !seg_intersect(p1, p2, q1, q2) {
        return None;
    }
    line_x(p1, p2, q1, q2).or(Some(p1))
}

/// 1 inside, 0 on the boundary, -1 outside (even-odd).
pub fn point_in_polygon(pt: P, ring: &[P]) -> i32 {
    let ring = open_ring(ring);
    let n = ring.len();
    if n < 3 {
        return -1;
    }
    let mut inside = false;
    for i in 0..n {
        let a = ring[i];
        let b = ring[(i + 1) % n];
        if cross(a, b, pt) == 0.0
            && pt[0] >= a[0].min(b[0])
            && pt[0] <= a[0].max(b[0])
            && pt[1] >= a[1].min(b[1])
            && pt[1] <= a[1].max(b[1])
        {
            return 0;
        }
        if (a[1] > pt[1]) != (b[1] > pt[1]) {
            let x = a[0] + (pt[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
            if pt[0] < x {
                inside = !inside;
            }
        }
    }
    if inside {
        1
    } else {
        -1
    }
}

/// The ring as GEOS sees it: open (no closing point) and without consecutive repeated points.
pub fn dedup_ring(ring: &[P]) -> Vec<P> {
    let mut out: Vec<P> = Vec::with_capacity(ring.len());
    for &p in ring {
        if out.last() != Some(&p) {
            out.push(p);
        }
    }
    while out.len() > 1 && out[0] == out[out.len() - 1] {
        out.pop();
    }
    out
}

/// shapely 2.2.0 `is_valid` of `shapely.polygons(ring)` (a shell, no holes), as GEOS IsValidOp
/// decides it: repeated points are ignored; fewer than three distinct points is "Too few
/// points"; any contact between non-adjacent edges, or adjacent edges that fold back on each
/// other (a spike, a zero-area ring), is a self-intersection. Self-touching rings are invalid.
pub fn ring_valid(ring: &[P]) -> bool {
    let r = dedup_ring(ring);
    let n = r.len();
    if n < 3 {
        return false;
    }
    for i in 0..n {
        let (a, b) = (r[i], r[(i + 1) % n]);
        // the next edge shares b: invalid only if it runs back along this one
        let c = r[(i + 2) % n];
        if cross(a, b, c) == 0.0
            && (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0.0
        {
            return false;
        }
        for j in (i + 2)..n {
            if i == 0 && j == n - 1 {
                continue;
            }
            let (c, d) = (r[j], r[(j + 1) % n]);
            if seg_intersect(a, b, c, d) {
                return false;
            }
        }
    }
    true
}

/// A polygonal region given by its boundary: directed edges with the region on their left.
/// `polygon(ring)` is the shapely polygon if `ring_valid`, else `buffer(polygon, 0)`; see
/// `Region::from_ring`.
#[derive(Debug, Clone, Default)]
pub struct Region {
    /// The deduplicated input ring (open) and its orientation sign (+1 CCW, -1 CW).
    ring: Vec<P>,
    sign: f64,
    /// Boundary edges, region on the left.
    edges: Vec<(P, P)>,
    /// The boundary edges chained into closed rings (outer rings CCW, holes CW).
    rings: Vec<Vec<P>>,
}

/// Winding number of `ring` at `p` along a ray towards +x (`vertical` false) or +y, half-open
/// at edge ends; edges whose index is in `skip` are left out.
fn winding(ring: &[P], p: P, vertical: bool, skip: &[usize]) -> i32 {
    let n = ring.len();
    let mut w = 0;
    for i in 0..n {
        if skip.contains(&i) {
            continue;
        }
        let (a, b) = (ring[i], ring[(i + 1) % n]);
        let c = cross(a, b, p);
        if !vertical {
            if a[1] <= p[1] && p[1] < b[1] && c > 0.0 {
                w += 1;
            } else if b[1] <= p[1] && p[1] < a[1] && c < 0.0 {
                w -= 1;
            }
        } else if b[0] <= p[0] && p[0] < a[0] && c > 0.0 {
            w += 1;
        } else if a[0] <= p[0] && p[0] < b[0] && c < 0.0 {
            w -= 1;
        }
    }
    w
}

fn on_segment(p: P, a: P, b: P) -> bool {
    cross(a, b, p) == 0.0
        && p[0] >= a[0].min(b[0])
        && p[0] <= a[0].max(b[0])
        && p[1] >= a[1].min(b[1])
        && p[1] <= a[1].max(b[1])
}

/// Parameter of `x` along p->q (x on the segment).
fn param(p: P, q: P, x: P) -> f64 {
    let d = [q[0] - p[0], q[1] - p[1]];
    if d[0].abs() > d[1].abs() {
        (x[0] - p[0]) / d[0]
    } else if d[1] != 0.0 {
        (x[1] - p[1]) / d[1]
    } else {
        0.0
    }
}

/// Reuse a pooled point within a relative 1e-9 of `x` so pieces of different edges share ends.
fn snap(pool: &mut Vec<P>, x: P) -> P {
    let tol = 1e-9 * (1.0 + x[0].abs().max(x[1].abs()));
    for &q in pool.iter() {
        if (q[0] - x[0]).abs() <= tol && (q[1] - x[1]).abs() <= tol {
            return q;
        }
    }
    pool.push(x);
    x
}

fn key(p: P) -> [u64; 2] {
    [p[0].to_bits(), p[1].to_bits()]
}

impl Region {
    /// shapely `polygons(ring)` when valid, else `buffer(polygon, 0)`. GEOS builds the zero
    /// buffer from the ring's offset curve with the ring's orientation taken from its signed
    /// area (zero counts as clockwise), so the result is the set of points whose winding number
    /// w has `sign * w >= 1`: one lobe of a bow-tie, the whole star of a pentagram (centre
    /// included), nothing for a zero-area ring, spikes dropped.
    pub fn from_ring(ring: &[P]) -> Region {
        let r = dedup_ring(ring);
        let sign = if signed_area(&r) > 0.0 { 1.0 } else { -1.0 };
        let mut reg = Region {
            ring: r,
            sign,
            ..Default::default()
        };
        if reg.ring.len() < 3 {
            return reg;
        }
        if ring_valid(&reg.ring) {
            let mut out = reg.ring.clone();
            if sign < 0.0 {
                out.reverse();
            }
            let n = out.len();
            reg.edges = (0..n).map(|i| (out[i], out[(i + 1) % n])).collect();
            reg.rings = vec![out];
            return reg;
        }
        reg.edges = reg.zero_buffer_edges();
        reg.rings = chain(&reg.edges);
        reg
    }

    /// Node the ring, then keep each piece that has the region on exactly one side.
    fn zero_buffer_edges(&self) -> Vec<(P, P)> {
        let r = &self.ring;
        let n = r.len();
        let mut pool: Vec<P> = r.clone();
        let mut cuts: Vec<Vec<P>> = (0..n).map(|i| vec![r[i], r[(i + 1) % n]]).collect();
        for i in 0..n {
            let (a, b) = (r[i], r[(i + 1) % n]);
            for j in (i + 1)..n {
                let (c, d) = (r[j], r[(j + 1) % n]);
                if !seg_intersect(a, b, c, d) {
                    continue;
                }
                if cross(a, b, c) == 0.0 && cross(a, b, d) == 0.0 {
                    // collinear overlap: each edge is cut at the other's ends
                    for x in [c, d] {
                        if on_segment(x, a, b) {
                            cuts[i].push(x);
                        }
                    }
                    for x in [a, b] {
                        if on_segment(x, c, d) {
                            cuts[j].push(x);
                        }
                    }
                    continue;
                }
                let x = [a, b, c, d]
                    .into_iter()
                    .find(|&v| on_segment(v, a, b) && on_segment(v, c, d))
                    .unwrap_or_else(|| line_x(a, b, c, d).unwrap_or(a));
                let x = snap(&mut pool, x);
                cuts[i].push(x);
                cuts[j].push(x);
            }
        }
        // unique undirected pieces: net direction count and the ring edges they lie on
        let mut pieces: Vec<(P, P, i32, Vec<usize>)> = Vec::new();
        let mut index: std::collections::HashMap<[u64; 4], usize> =
            std::collections::HashMap::new();
        for (i, pts) in cuts.iter_mut().enumerate() {
            let (a, b) = (r[i], r[(i + 1) % n]);
            pts.sort_by(|x, y| param(a, b, *x).total_cmp(&param(a, b, *y)));
            pts.dedup();
            for w in pts.windows(2) {
                let (p, q) = (w[0], w[1]);
                let fwd = (key(p), p) < (key(q), q);
                let (lo, hi) = if fwd { (p, q) } else { (q, p) };
                let k = [key(lo)[0], key(lo)[1], key(hi)[0], key(hi)[1]];
                let slot = *index.entry(k).or_insert_with(|| {
                    pieces.push((lo, hi, 0, Vec::new()));
                    pieces.len() - 1
                });
                pieces[slot].2 += if fwd { 1 } else { -1 };
                pieces[slot].3.push(i);
            }
        }
        let inside = |w: i32| self.sign * w as f64 >= 1.0;
        let mut edges = Vec::new();
        for (a, b, net, on) in pieces {
            if net == 0 {
                continue; // the same winding on both sides
            }
            let m = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0];
            // winding just beside m (to +x, or to +y for a horizontal piece), then the other side
            let (wl, wr) = if a[1] != b[1] {
                let w = winding(r, m, false, &on);
                if b[1] > a[1] {
                    (w + net, w)
                } else {
                    (w, w - net)
                }
            } else {
                let w = winding(r, m, true, &on);
                if b[0] > a[0] {
                    (w, w - net)
                } else {
                    (w + net, w)
                }
            };
            match (inside(wl), inside(wr)) {
                (true, false) => edges.push((a, b)),
                (false, true) => edges.push((b, a)),
                _ => {}
            }
        }
        edges
    }

    pub fn is_empty(&self) -> bool {
        self.edges.is_empty()
    }

    pub fn bounds(&self) -> [f64; 4] {
        let pts: Vec<P> = self.edges.iter().map(|e| e.0).collect();
        bounds(&pts)
    }

    #[cfg(test)]
    pub fn area(&self) -> f64 {
        self.rings.iter().map(|r| signed_area(r)).sum()
    }

    /// 1 inside, 0 on the boundary, -1 outside.
    pub fn locate(&self, p: P) -> i32 {
        if self.edges.iter().any(|&(a, b)| on_segment(p, a, b)) {
            return 0;
        }
        if self.is_empty() {
            return -1;
        }
        if self.sign * winding(&self.ring, p, false, &[]) as f64 >= 1.0 {
            1
        } else {
            -1
        }
    }

    /// `intersects` with a convex polygon (boundary contact counts).
    pub fn intersects_convex(&self, core: &[P]) -> bool {
        let core = open_ring(core);
        if self.is_empty() || core.is_empty() {
            return false;
        }
        let n = core.len();
        for &(a, b) in &self.edges {
            for j in 0..n {
                if seg_intersect(a, b, core[j], core[(j + 1) % n]) {
                    return true;
                }
            }
        }
        // no edge contact: the core lies in the region, or a whole ring lies in the core
        self.locate(core[0]) >= 0 || self.rings.iter().any(|r| point_in_polygon(r[0], core) >= 0)
    }

    /// Area of the intersection with a convex polygon (each boundary ring clipped, signed sum).
    pub fn clip_area(&self, core: &[P]) -> f64 {
        let s: f64 = self
            .rings
            .iter()
            .map(|r| signed_area(&clip_convex(r, core)))
            .sum();
        s.max(0.0)
    }

    /// Bounds of `core \ region` (core convex): the boundary pieces of the difference.
    pub fn difference_bounds(&self, core: &[P]) -> Option<[f64; 4]> {
        let core = open_ring(core);
        let n = core.len();
        let core_edges: Vec<(P, P)> = (0..n).map(|i| (core[i], core[(i + 1) % n])).collect();
        let mut pts: Vec<P> = Vec::new();
        for &(p, q) in &core_edges {
            pieces_where(p, q, &self.edges, |m| self.locate(m) < 0, &mut pts);
        }
        for &(p, q) in &self.edges {
            pieces_where(
                p,
                q,
                &core_edges,
                |m| point_in_polygon(m, core) > 0,
                &mut pts,
            );
        }
        if pts.is_empty() {
            None
        } else {
            Some(bounds(&pts))
        }
    }
}

/// Split p-q at its contacts with `others`; push the ends of each piece whose midpoint `keep`s.
fn pieces_where(p: P, q: P, others: &[(P, P)], keep: impl Fn(P) -> bool, out: &mut Vec<P>) {
    let mut ts = vec![0.0, 1.0];
    for &(a, b) in others {
        if let Some(x) = seg_point(p, q, a, b) {
            ts.push(param(p, q, x).clamp(0.0, 1.0));
        }
        for v in [a, b] {
            if on_segment(v, p, q) {
                ts.push(param(p, q, v).clamp(0.0, 1.0));
            }
        }
    }
    ts.sort_by(|a, b| a.total_cmp(b));
    let at = |t: f64| [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    for w in ts.windows(2) {
        if w[1] > w[0] && keep(at((w[0] + w[1]) / 2.0)) {
            out.push(at(w[0]));
            out.push(at(w[1]));
        }
    }
}

/// Chain directed edges into closed rings (end point to an unused edge starting there).
fn chain(edges: &[(P, P)]) -> Vec<Vec<P>> {
    let mut from: std::collections::HashMap<[u64; 2], Vec<usize>> =
        std::collections::HashMap::new();
    for (i, e) in edges.iter().enumerate() {
        from.entry(key(e.0)).or_default().push(i);
    }
    let mut used = vec![false; edges.len()];
    let mut rings = Vec::new();
    for s in 0..edges.len() {
        if used[s] {
            continue;
        }
        used[s] = true;
        let start = edges[s].0;
        let mut ring = vec![start];
        let mut at = edges[s].1;
        while at != start {
            ring.push(at);
            let next = from
                .get(&key(at))
                .and_then(|l| l.iter().copied().find(|&i| !used[i]));
            match next {
                Some(i) => {
                    used[i] = true;
                    at = edges[i].1;
                }
                None => break, // not closed (rounding); clipping closes it
            }
        }
        rings.push(ring);
    }
    rings
}

/// Bounds of `core \\ node` for a raw ring `node`: the buffer(0) region's difference bounds.
/// Kept for the crate's unit tests; the checker calls `Region::difference_bounds`.
#[cfg(test)]
pub fn difference_bounds(core: &[P], node: &[P]) -> Option<[f64; 4]> {
    Region::from_ring(node).difference_bounds(core)
}

/// Uniform grid over boxes for "boxes intersect" candidate pairs (STRtree stand-in).
pub struct Grid {
    cell: f64,
    x0: f64,
    y0: f64,
    nx: usize,
    ny: usize,
    cells: Vec<Vec<u32>>,
    boxes: Vec<[f64; 4]>,
    stamp: Vec<u32>,
    epoch: u32,
}

impl Grid {
    pub fn new(boxes: Vec<[f64; 4]>, cell: f64) -> Grid {
        let mut b = [
            f64::INFINITY,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
        ];
        for x in &boxes {
            if x.iter().all(|v| v.is_finite()) {
                b[0] = b[0].min(x[0]);
                b[1] = b[1].min(x[1]);
                b[2] = b[2].max(x[2]);
                b[3] = b[3].max(x[3]);
            }
        }
        if !b[0].is_finite() {
            b = [0.0, 0.0, 1.0, 1.0];
        }
        let mut cell = cell.max(1e-3);
        while ((b[2] - b[0]) / cell) * ((b[3] - b[1]) / cell) > 4.0e6 {
            cell *= 2.0;
        }
        let nx = (((b[2] - b[0]) / cell) as usize + 1).max(1);
        let ny = (((b[3] - b[1]) / cell) as usize + 1).max(1);
        let mut g = Grid {
            cell,
            x0: b[0],
            y0: b[1],
            nx,
            ny,
            cells: vec![Vec::new(); nx * ny],
            stamp: vec![0; boxes.len()],
            boxes,
            epoch: 0,
        };
        for i in 0..g.boxes.len() {
            let bx = g.boxes[i];
            if !bx.iter().all(|v| v.is_finite()) {
                continue;
            }
            let (ax, ay, bx2, by2) = g.range(&bx);
            for y in ay..=by2 {
                for x in ax..=bx2 {
                    g.cells[y * nx + x].push(i as u32);
                }
            }
        }
        g
    }

    fn range(&self, b: &[f64; 4]) -> (usize, usize, usize, usize) {
        let c =
            |v: f64, o: f64, n: usize| (((v - o) / self.cell).floor().max(0.0) as usize).min(n - 1);
        (
            c(b[0], self.x0, self.nx),
            c(b[1], self.y0, self.ny),
            c(b[2], self.x0, self.nx),
            c(b[3], self.y0, self.ny),
        )
    }

    /// Tree indices whose box intersects `b` (closed), ascending.
    pub fn query(&mut self, b: &[f64; 4], out: &mut Vec<usize>) {
        out.clear();
        if !b.iter().all(|v| v.is_finite()) {
            return;
        }
        self.epoch = self.epoch.wrapping_add(1);
        let (ax, ay, bx, by) = self.range(b);
        for y in ay..=by {
            for x in ax..=bx {
                for &i in &self.cells[y * self.nx + x] {
                    let i = i as usize;
                    if self.stamp[i] == self.epoch {
                        continue;
                    }
                    self.stamp[i] = self.epoch;
                    let o = &self.boxes[i];
                    if o[0] <= b[2] && b[0] <= o[2] && o[1] <= b[3] && b[1] <= o[3] {
                        out.push(i);
                    }
                }
            }
        }
        out.sort_unstable();
    }
}

/// 2-D kd-tree for k nearest neighbours (scipy cKDTree stand-in; ties by index).
pub struct KdTree {
    pts: Vec<P>,
    idx: Vec<usize>,
}

impl KdTree {
    pub fn new(pts: &[P]) -> KdTree {
        let mut idx: Vec<usize> = (0..pts.len()).collect();
        Self::build(pts, &mut idx, 0);
        KdTree {
            pts: pts.to_vec(),
            idx,
        }
    }

    fn build(pts: &[P], idx: &mut [usize], depth: usize) {
        if idx.len() <= 1 {
            return;
        }
        let axis = depth % 2;
        let mid = idx.len() / 2;
        idx.select_nth_unstable_by(mid, |a, b| {
            pts[*a][axis].total_cmp(&pts[*b][axis]).then(a.cmp(b))
        });
        let (l, r) = idx.split_at_mut(mid);
        Self::build(pts, l, depth + 1);
        Self::build(pts, &mut r[1..], depth + 1);
    }

    /// The k nearest points to point `q` (sorted by distance, then index).
    pub fn knn(&self, q: P, k: usize, out: &mut Vec<(f64, usize)>) {
        out.clear();
        if k == 0 {
            return;
        }
        self.search(&self.idx, 0, q, k, out);
    }

    fn worse(a: &(f64, usize), b: &(f64, usize)) -> bool {
        a.0 > b.0 || (a.0 == b.0 && a.1 > b.1)
    }

    fn search(&self, idx: &[usize], depth: usize, q: P, k: usize, out: &mut Vec<(f64, usize)>) {
        if idx.is_empty() {
            return;
        }
        let axis = depth % 2;
        let mid = idx.len() / 2;
        let i = idx[mid];
        let p = self.pts[i];
        let d = (p[0] - q[0]).powi(2) + (p[1] - q[1]).powi(2);
        let cand = (d, i);
        if out.len() < k {
            let pos = out.partition_point(|x| !Self::worse(x, &cand));
            out.insert(pos, cand);
        } else if let Some(last) = out.last() {
            if Self::worse(last, &cand) {
                out.pop();
                let pos = out.partition_point(|x| !Self::worse(x, &cand));
                out.insert(pos, cand);
            }
        }
        let diff = q[axis] - p[axis];
        let (near, far) = if diff < 0.0 {
            (&idx[..mid], &idx[mid + 1..])
        } else {
            (&idx[mid + 1..], &idx[..mid])
        };
        self.search(near, depth + 1, q, k, out);
        let bound = out.last().map(|x| x.0).unwrap_or(f64::INFINITY);
        if out.len() < k || diff * diff <= bound {
            self.search(far, depth + 1, q, k, out);
        }
    }
}

/// Union-find components labelled in order of their smallest member (scipy order).
pub fn components(n: usize, edges: impl Iterator<Item = (usize, usize)>) -> (usize, Vec<usize>) {
    let mut parent: Vec<usize> = (0..n).collect();
    fn find(p: &mut [usize], mut x: usize) -> usize {
        while p[x] != x {
            p[x] = p[p[x]];
            x = p[x];
        }
        x
    }
    for (a, b) in edges {
        let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
        if ra != rb {
            let (lo, hi) = if ra < rb { (ra, rb) } else { (rb, ra) };
            parent[hi] = lo;
        }
    }
    let mut label = vec![usize::MAX; n];
    let mut labels = vec![0; n];
    let mut count = 0;
    for (i, slot) in labels.iter_mut().enumerate() {
        let r = find(&mut parent, i);
        if label[r] == usize::MAX {
            label[r] = count;
            count += 1;
        }
        *slot = label[r];
    }
    (count, labels)
}

/// numpy's pairwise summation (`np.add.reduce` on a contiguous float64 vector).
pub fn np_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut s = 0.0;
        for &x in a {
            s += x;
        }
        // numpy starts from -0.0 for an empty reduce only in odd cases; 0.0 is fine here
        s
    } else if n <= 128 {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        np_sum(&a[..n2]) + np_sum(&a[n2..])
    }
}

#[cfg(test)]
mod tests {
    //! Expected values are shapely 2.2.0 (GEOS) answers for the same rings.
    use super::*;

    fn ring(pts: &[(f64, f64)]) -> Vec<P> {
        pts.iter().map(|&(x, y)| [x, y]).collect()
    }

    fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<P> {
        vec![[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    }

    fn near(a: f64, b: f64) -> bool {
        (a - b).abs() < 1e-6
    }

    const A: &[(f64, f64)] = &[
        (109., 609.),
        (206., 625.),
        (135., 613.),
        (101., 598.),
        (191., 648.),
    ];
    const D: &[(f64, f64)] = &[
        (191., 601.),
        (169., 649.),
        (210., 625.),
        (180., 600.),
        (127., 631.),
        (133., 602.),
    ];
    const BOW: &[(f64, f64)] = &[(100., 600.), (220., 640.), (220., 600.), (100., 640.)];
    const BOWR: &[(f64, f64)] = &[(100., 640.), (220., 600.), (220., 640.), (100., 600.)];
    const PENT: &[(f64, f64)] = &[
        (160., 650.),
        (190., 580.),
        (110., 625.),
        (210., 625.),
        (130., 580.),
    ];
    const FIG8: &[(f64, f64)] = &[
        (0., 0.),
        (2., 0.),
        (2., 2.),
        (4., 2.),
        (4., 4.),
        (2., 4.),
        (2., 2.),
        (0., 2.),
    ];
    const SPIKE: &[(f64, f64)] = &[
        (100., 600.),
        (220., 600.),
        (220., 640.),
        (160., 640.),
        (160., 700.),
        (160., 640.),
        (100., 640.),
    ];
    const TOUCH: &[(f64, f64)] = &[(0., 0.), (4., 0.), (4., 4.), (2., 0.), (0., 4.)];
    const ANNULUS: &[(f64, f64)] = &[
        (0., 0.),
        (10., 0.),
        (10., 10.),
        (0., 10.),
        (0., 0.),
        (3., 3.),
        (3., 7.),
        (7., 7.),
        (7., 3.),
        (3., 3.),
    ];

    #[test]
    fn ring_valid_follows_geos_is_valid() {
        let valid: &[&[(f64, f64)]] = &[
            &[
                (100., 600.),
                (100., 600.),
                (220., 600.),
                (220., 600.),
                (220., 640.),
                (100., 640.),
                (100., 640.),
            ],
            &[(105., 620.), (145., 595.), (120., 590.), (120., 590.)],
            &[
                (130., 590.),
                (110., 610.),
                (110., 610.),
                (100., 620.),
                (160., 590.),
            ],
            &[(0., 0.), (1., 0.), (1., 1.), (0., 1.), (0., 0.)],
        ];
        for r in valid {
            assert!(ring_valid(&ring(r)), "{r:?}");
        }
        let invalid: &[&[(f64, f64)]] = &[
            A,
            D,
            BOW,
            BOWR,
            PENT,
            FIG8,
            SPIKE,
            TOUCH,
            ANNULUS,
            &[(100., 600.), (160., 600.), (220., 600.), (160., 600.)],
            &[(100., 600.), (160., 620.), (220., 640.), (160., 620.)],
            &[(0., 0.), (2., 0.), (1., 0.)],
            &[(0., 0.), (1., 1.), (0., 0.)],
        ];
        for r in invalid {
            assert!(!ring_valid(&ring(r)), "{r:?}");
        }
    }

    #[test]
    fn zero_buffer_areas_match_geos() {
        for (r, want) in [
            (A, 213.766862),
            (D, 676.93532),
            (BOW, 1200.0),
            (BOWR, 1200.0),
            (PENT, 2293.261819),
            (FIG8, 8.0),
            (SPIKE, 4800.0),
            (TOUCH, 8.0),
            (ANNULUS, 84.0),
        ] {
            let g = Region::from_ring(&ring(r));
            assert!(near(g.area(), want), "{r:?}: {} != {want}", g.area());
        }
        for r in [
            &[(100., 600.), (160., 600.), (220., 600.), (160., 600.)][..],
            &[(100., 600.), (160., 620.), (220., 640.), (160., 620.)],
            &[(0., 0.), (2., 0.), (1., 0.)],
        ] {
            assert!(Region::from_ring(&ring(r)).is_empty(), "{r:?}");
        }
    }

    #[test]
    fn bow_tie_keeps_the_clockwise_lobe() {
        // signed area 0 counts as clockwise: BOW keeps the right lobe, BOWR the left one
        let c = rect(150., 605., 200., 630.);
        let (b, br) = (
            Region::from_ring(&ring(BOW)),
            Region::from_ring(&ring(BOWR)),
        );
        assert!(near(b.clip_area(&c), 516.666667));
        assert!(near(br.clip_area(&c), 33.333333));
        assert_eq!(b.locate([200., 620.]), 1);
        assert_eq!(b.locate([120., 620.]), -1);
        assert_eq!(br.locate([120., 620.]), 1);
    }

    #[test]
    fn clip_area_intersects_and_difference_bounds_match_geos() {
        let c1 = rect(150., 605., 200., 630.);
        let c2 = rect(0., 0., 3., 3.);
        let a = Region::from_ring(&ring(A));
        assert!(near(a.clip_area(&c1), 18.17906));
        assert!(a.intersects_convex(&c1) && !a.intersects_convex(&c2));
        let d = Region::from_ring(&ring(D));
        assert!(near(d.clip_area(&c1), 137.601965));
        let p = Region::from_ring(&ring(PENT));
        assert!(near(p.clip_area(&c1), 917.464243));
        assert_eq!(p.difference_bounds(&c1), Some([150., 605., 200., 630.]));
        // self-touching: the bottom touch point splits the lobes; c2 \ region starts at x=0.5
        let t = Region::from_ring(&ring(TOUCH));
        assert!(near(t.clip_area(&c2), 4.75));
        let b = t.difference_bounds(&c2).unwrap();
        assert!(
            near(b[0], 0.5) && near(b[1], 0.) && near(b[2], 3.) && near(b[3], 3.),
            "{b:?}"
        );
        let f = Region::from_ring(&ring(FIG8));
        assert!(near(f.clip_area(&c2), 5.0) && f.intersects_convex(&c2));
        // the spike is dropped: the rectangle covers c1, nothing is left over
        let s = Region::from_ring(&ring(SPIKE));
        assert!(near(s.clip_area(&c1), 1250.0));
        assert_eq!(s.difference_bounds(&c1), None);
        // the hole of the slit ring stays a hole; c2 lies in the solid part
        let an = Region::from_ring(&ring(ANNULUS));
        assert!(near(an.clip_area(&c2), 9.0));
        assert_eq!(an.difference_bounds(&c2), None);
        assert_eq!(an.locate([5., 5.]), -1);
    }
}
