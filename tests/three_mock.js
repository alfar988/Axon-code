// Minimal functional stand-in for the parts of Three.js r128 that the templates use. It lets the harness run game logic
// (positions, collisions) without WebGL. Only names that exist in r128 are defined: anything else would throw in a test.
"use strict";
class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  copy(v) { return this.set(v.x, v.y, v.z); }
  clone() { return new Vector3(this.x, this.y, this.z); }
  add(v) { this.x += v.x; this.y += v.y; this.z += v.z; return this; }
  sub(v) { this.x -= v.x; this.y -= v.y; this.z -= v.z; return this; }
  multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
  length() { return Math.hypot(this.x, this.y, this.z); }
  normalize() { const l = this.length() || 1; return this.multiplyScalar(1 / l); }
  distanceTo(v) { return Math.hypot(this.x - v.x, this.y - v.y, this.z - v.z); }
  lerp(v, t) { this.x += (v.x - this.x) * t; this.y += (v.y - this.y) * t; this.z += (v.z - this.z) * t; return this; }
}
class Object3D {
  constructor() { this.position = new Vector3(); this.rotation = new Vector3(); this.scale = new Vector3(1, 1, 1); this.children = []; this.visible = true; this.userData = {}; this.parent = null; }
  add(...o) { o.forEach((x) => { this.children.push(x); x.parent = this; }); return this; }
  remove(o) { const i = this.children.indexOf(o); if (i >= 0) this.children.splice(i, 1); return this; }
  lookAt() {}
}
const geo = () => class { constructor(...a) { this.args = a; } dispose() {} };
const mat = () => class { constructor(p) { Object.assign(this, p || {}); } dispose() {} };
class Scene extends Object3D { constructor() { super(); this.fog = null; this.background = null; } }
class Mesh extends Object3D { constructor(g, m) { super(); this.geometry = g; this.material = m; } }
class PerspectiveCamera extends Object3D { constructor(fov, aspect) { super(); this.fov = fov; this.aspect = aspect; } updateProjectionMatrix() {} }
class Light extends Object3D { constructor(...a) { super(); this.args = a; } }
class WebGLRenderer { constructor() { this.domElement = {}; } setSize() {} setPixelRatio() {} setClearColor() {} render() { this.rendered = (this.rendered || 0) + 1; } dispose() {} }
module.exports = {
  Vector3, Object3D, Scene, Mesh, PerspectiveCamera, WebGLRenderer, Group: class extends Object3D {},
  HemisphereLight: Light, DirectionalLight: Light, AmbientLight: Light, PointLight: Light, Fog: class { constructor(c, n, f) { this.color = c; this.near = n; this.far = f; } },
  GridHelper: class extends Object3D { constructor(...a) { super(); this.args = a; } },
  OctahedronGeometry: geo(), SphereGeometry: geo(), CylinderGeometry: geo(), BoxGeometry: geo(), CircleGeometry: geo(), RingGeometry: geo(), PlaneGeometry: geo(),
  MeshStandardMaterial: mat(), MeshBasicMaterial: mat(), MeshLambertMaterial: mat(), Color: class { constructor(c) { this.c = c; } },
  Clock: class { getDelta() { return 0.016; } }
};
