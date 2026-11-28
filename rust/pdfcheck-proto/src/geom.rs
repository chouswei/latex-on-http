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
    let mut b = [f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY];
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
    if ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0)) && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0)) {
        return true;
    }
    let on = |a: P, b: P, c: P| {
        c[0] >= a[0].min(b[0]) && c[0] <= a[0].max(b[0]) && c[1] >= a[1].min(b[1]) && c[1] <= a[1].max(b[1])
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

/// shapely `is_valid` approximation for a simple ring: enough points, non-zero area,
/// no crossing between non-adjacent edges.
pub fn ring_valid(ring: &[P]) -> bool {
    let r = open_ring(ring);
    let n = r.len();
    if n < 3 || area(r) == 0.0 {
        return false;
    }
    for i in 0..n {
        let (a, b) = (r[i], r[(i + 1) % n]);
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

/// Do two polygons (rings) intersect (boundary contact counts)?
pub fn polygons_intersect(a: &[P], b: &[P]) -> bool {
    let (a, b) = (open_ring(a), open_ring(b));
    if a.is_empty() || b.is_empty() {
        return false;
    }
    let (ba, bb) = (bounds(a), bounds(b));
    if ba[2] < bb[0] || bb[2] < ba[0] || ba[3] < bb[1] || bb[3] < ba[1] {
        return false;
    }
    for i in 0..a.len() {
        let (p, q) = (a[i], a[(i + 1) % a.len()]);
        for j in 0..b.len() {
            if seg_intersect(p, q, b[j], b[(j + 1) % b.len()]) {
                return true;
            }
        }
    }
    point_in_polygon(a[0], b) >= 0 || point_in_polygon(b[0], a) >= 0
}

/// Bounds of `core \ node` (core convex): the boundary pieces of the difference.
pub fn difference_bounds(core: &[P], node: &[P]) -> Option<[f64; 4]> {
    let (core, node) = (open_ring(core), open_ring(node));
    let mut pts: Vec<P> = Vec::new();
    let split = |p: P, q: P, other: &[P]| -> Vec<f64> {
        let mut ts = vec![0.0, 1.0];
        let d = [q[0] - p[0], q[1] - p[1]];
        for j in 0..other.len() {
            let (a, b) = (other[j], other[(j + 1) % other.len()]);
            if let Some(x) = seg_point(p, q, a, b) {
                let t = if d[0].abs() > d[1].abs() {
                    (x[0] - p[0]) / d[0]
                } else if d[1] != 0.0 {
                    (x[1] - p[1]) / d[1]
                } else {
                    0.0
                };
                ts.push(t.clamp(0.0, 1.0));
            }
        }
        ts.sort_by(|a, b| a.total_cmp(b));
        ts
    };
    let at = |p: P, q: P, t: f64| [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    for i in 0..core.len() {
        let (p, q) = (core[i], core[(i + 1) % core.len()]);
        let ts = split(p, q, node);
        for w in ts.windows(2) {
            let mid = at(p, q, (w[0] + w[1]) / 2.0);
            if w[1] > w[0] && point_in_polygon(mid, node) < 0 {
                pts.push(at(p, q, w[0]));
                pts.push(at(p, q, w[1]));
            }
        }
    }
    for i in 0..node.len() {
        let (p, q) = (node[i], node[(i + 1) % node.len()]);
        let ts = split(p, q, core);
        for w in ts.windows(2) {
            let mid = at(p, q, (w[0] + w[1]) / 2.0);
            if w[1] > w[0] && point_in_polygon(mid, core) > 0 {
                pts.push(at(p, q, w[0]));
                pts.push(at(p, q, w[1]));
            }
        }
    }
    if pts.is_empty() {
        None
    } else {
        Some(bounds(&pts))
    }
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
        let mut b = [f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY];
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
        let c = |v: f64, o: f64, n: usize| (((v - o) / self.cell).floor().max(0.0) as usize).min(n - 1);
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
        KdTree { pts: pts.to_vec(), idx }
    }

    fn build(pts: &[P], idx: &mut [usize], depth: usize) {
        if idx.len() <= 1 {
            return;
        }
        let axis = depth % 2;
        let mid = idx.len() / 2;
        idx.select_nth_unstable_by(mid, |a, b| pts[*a][axis].total_cmp(&pts[*b][axis]).then(a.cmp(b)));
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
    for i in 0..n {
        let r = find(&mut parent, i);
        if label[r] == usize::MAX {
            label[r] = count;
            count += 1;
        }
        labels[i] = label[r];
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
