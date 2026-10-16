/**
 * schema_lite.mjs — minimal Draft-2020-12 subset validator (zero-dependency).
 *
 * Supports EXACTLY the keyword set used by the landed public contracts this
 * reference validates against (api-schemas/instruction-envelope.schema.json,
 * api-schemas/permissions.schema.json):
 *   $defs/$ref (local), type, enum, const, pattern, minLength/maxLength,
 *   minimum/maximum (+exclusive), items, minItems/maxItems, uniqueItems,
 *   properties, required, additionalProperties:false, allOf, if/then.
 *
 * `format` is annotation-only in Draft 2020-12 (verified against the repo's
 * validate_schemas.py semantics) — matched but not enforced.
 *
 * SSOT doctrine: the SCHEMA files are the contract; this validator is a
 * stdlib-only executor for them. Any keyword outside the supported set makes
 * the validator FAIL CLOSED (unknown keyword -> schema rejected), so a schema
 * drift can never silently weaken validation.
 */

const SUPPORTED_KEYWORDS = new Set([
  "$defs", "$id", "$schema", "$ref", "title", "description", "format",
  "type", "enum", "const", "pattern", "minLength", "maxLength",
  "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
  "items", "minItems", "maxItems", "uniqueItems", "contains",
  "properties", "required", "additionalProperties",
  "allOf", "if", "then",
]);

const TYPES = new Set(["object", "array", "string", "number", "integer",
  "boolean", "null"]);

/** Validate a schema document itself — unknown keywords fail closed. */
export function checkSchema(schema, root = schema, path = "") {
  if (Array.isArray(schema)) {
    schema.forEach((item, i) => checkSchema(item, root, `${path}/${i}`));
    return;
  }
  if (schema === null || typeof schema !== "object" || Array.isArray(schema)) {
    if (typeof schema === "boolean") return; // true/false schemas are legal
    throw new Error(`schema_lite: schema node must be an object at ${path}`);
  }
  for (const key of Object.keys(schema)) {
    if (!SUPPORTED_KEYWORDS.has(key)) {
      throw new Error(`schema_lite: unsupported keyword '${key}' at ${path} (fail-closed)`);
    }
  }
  if (schema.$ref !== undefined) {
    if (typeof schema.$ref !== "string" || !schema.$ref.startsWith("#/$defs/")) {
      throw new Error(`schema_lite: only local #/$defs/ refs supported at ${path}`);
    }
    return;
  }
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    for (const t of types) {
      if (!TYPES.has(t)) throw new Error(`schema_lite: unknown type '${t}' at ${path}`);
    }
  }
  for (const key of ["properties", "$defs"]) {
    const node = schema[key];
    if (node !== undefined) {
      for (const name of Object.keys(node)) checkSchema(node[name], root, `${path}/${key}/${name}`);
    }
  }
  for (const key of ["items", "if", "then", "additionalProperties"]) {
    if (schema[key] !== undefined && typeof schema[key] === "object") {
      checkSchema(schema[key], root, `${path}/${key}`);
    }
  }
  if (schema.allOf !== undefined) checkSchema(schema.allOf, root, `${path}/allOf`);
}

function resolveRef(ref, root) {
  const segs = ref.replace(/^#\//, "").split("/");
  let node = root;
  for (const seg of segs) {
    node = node?.[seg];
    if (node === undefined) throw new Error(`schema_lite: unresolvable $ref ${ref}`);
  }
  return node;
}

function typeOf(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
}

function typeMatches(value, expected) {
  const actual = typeOf(value);
  if (Array.isArray(expected)) return expected.some((t) => typeMatches(value, t));
  if (expected === "number") return actual === "number" || actual === "integer";
  return actual === expected;
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Validate `value` against `schema` (with $root for $ref resolution).
 * @returns {string[]} errors — empty list = valid
 */
export function validate(value, schema, root = null, path = "") {
  const errors = [];
  const r = root || schema;

  if (schema === true) return errors;
  if (schema === false) {
    errors.push(`${path || "/"}: schema false admits nothing`);
    return errors;
  }

  if (schema.$ref !== undefined) {
    return validate(value, resolveRef(schema.$ref, r), r, path);
  }

  if (schema.type !== undefined && !typeMatches(value, schema.type)) {
    errors.push(`${path || "/"}: expected type ${JSON.stringify(schema.type)}, got ${typeOf(value)}`);
    return errors; // type mismatch makes deeper checks noise
  }
  if (schema.const !== undefined && !deepEqual(value, schema.const)) {
    errors.push(`${path || "/"}: const mismatch (expected ${JSON.stringify(schema.const)})`);
  }
  if (schema.enum !== undefined && !schema.enum.some((v) => deepEqual(v, value))) {
    errors.push(`${path || "/"}: value not in enum [${schema.enum.map((v) => JSON.stringify(v)).join(", ")}]`);
  }
  if (typeof value === "string") {
    if (schema.pattern !== undefined && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path || "/"}: string does not match pattern ${schema.pattern}`);
    }
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path || "/"}: minLength ${schema.minLength} violated`);
    }
    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      errors.push(`${path || "/"}: maxLength ${schema.maxLength} violated`);
    }
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(`${path || "/"}: minimum violated`);
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(`${path || "/"}: maximum violated`);
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) {
      errors.push(`${path || "/"}: exclusiveMinimum violated`);
    }
    if (schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) {
      errors.push(`${path || "/"}: exclusiveMaximum violated`);
    }
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path || "/"}: minItems ${schema.minItems} violated`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path || "/"}: maxItems ${schema.maxItems} violated`);
    }
    if (schema.uniqueItems) {
      const seen = new Set(value.map((v) => JSON.stringify(v)));
      if (seen.size !== value.length) errors.push(`${path || "/"}: uniqueItems violated`);
    }
    if (schema.items !== undefined) {
      value.forEach((item, i) => errors.push(...validate(item, schema.items, r, `${path}/${i}`)));
    }
    if (schema.contains !== undefined) {
      const anyMatch = value.some((item) => validate(item, schema.contains, r, path).length === 0);
      if (!anyMatch) errors.push(`${path || "/"}: no item matches the 'contains' schema`);
    }
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const props = schema.properties || {};
    for (const name of schema.required || []) {
      if (!(name in value)) errors.push(`${path || "/"}: missing required property '${name}'`);
    }
    if (schema.additionalProperties === false) {
      for (const name of Object.keys(value)) {
        if (!(name in props)) {
          errors.push(`${path || "/"}: additional property not allowed: '${name}'`);
        }
      }
    }
    for (const name of Object.keys(props)) {
      if (name in value) {
        errors.push(...validate(value[name], props[name], r, `${path}/${name}`));
      }
    }
  }
  if (schema.allOf !== undefined) {
    for (const sub of schema.allOf) errors.push(...validate(value, sub, r, path));
  }
  if (schema.if !== undefined) {
    const matches = validate(value, schema.if, r, path).length === 0;
    if (matches && schema.then !== undefined) {
      errors.push(...validate(value, schema.then, r, path));
    }
  }
  return errors;
}

/** Convenience: check the schema once, then validate a payload. */
export function makeValidator(schema) {
  checkSchema(schema);
  return (payload) => validate(payload, schema, schema, "");
}
