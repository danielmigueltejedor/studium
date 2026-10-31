var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __esm = (fn, res) => function __init() {
  return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// node_modules/ts-fsrs/dist/schema-utils-DX7uVwiJ.mjs
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
function roundTo(num, decimals) {
  const factor = 10 ** decimals;
  return Math.round(num * factor) / factor;
}
function isObject(value) {
  return typeof value === "object" && value !== null;
}
function isNumberArray(value) {
  if (!Array.isArray(value)) return false;
  for (const item of value) if (typeof item !== "number" || !Number.isFinite(item)) return false;
  return true;
}
var init_schema_utils_DX7uVwiJ = __esm({
  "node_modules/ts-fsrs/dist/schema-utils-DX7uVwiJ.mjs"() {
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/schema-CgTDED3c.js
function isObject2(value) {
  return !!value && !Array.isArray(value) && typeof value === "object";
}
function isFiniteNumber(value) {
  return Number.isFinite(value);
}
function isFunction(fn) {
  return typeof fn === "function";
}
function defineOwnDataField(target, key, value) {
  const record = target;
  if (key in target) {
    const existing = Object.getOwnPropertyDescriptor(target, key);
    if (existing && "value" in existing && existing.writable) {
      record[key] = value;
      return;
    }
  } else {
    const prototype = Object.getPrototypeOf(target);
    if (prototype === Object.prototype || prototype === null) {
      record[key] = value;
      return;
    }
  }
  Object.defineProperty(target, key, {
    value,
    writable: true,
    enumerable: true,
    configurable: true
  });
}
function assignObjectFields(target, source) {
  const fields = source;
  for (const key in fields) if (Object.hasOwn(fields, key)) defineOwnDataField(target, key, fields[key]);
}
function assignEnumerableDataFields(target, ...sources) {
  for (const source of sources) {
    if (source == null) continue;
    const fields = Object(source);
    assignObjectFields(target, fields);
    for (const key of Object.getOwnPropertySymbols(fields)) {
      if (!Object.getOwnPropertyDescriptor(fields, key)?.enumerable) continue;
      defineOwnDataField(target, key, fields[key]);
    }
  }
  return target;
}
function isPromiseLike(value) {
  return "then" in value && typeof value.then === "function";
}
function validateSync(schema, input) {
  const result = schema["~standard"].validate(input);
  if (isPromiseLike(result)) {
    Promise.resolve(result).catch((error) => {
      console.error("Async Standard Schema validation rejected", error);
    });
    throw new TypeError("Async Standard Schema validation is not supported");
  }
  return result;
}
function defineSchema(validate) {
  return {
    "~standard": {
      version: 1,
      vendor: "@open-spaced-repetition/srs-kit",
      validate
    },
    parse(input) {
      const result = validate(input);
      if (result.issues) throw new SRSSchemaError(result.issues);
      return result.value;
    },
    safeParse(input) {
      const result = validate(input);
      if (result.issues) return {
        success: false,
        issues: result.issues
      };
      return {
        success: true,
        data: result.value
      };
    }
  };
}
function parse(schema, input) {
  const result = validateSync(schema, input);
  if (result.issues) throw new SRSSchemaError(result.issues);
  return result.value;
}
function isValidDate(value) {
  return value instanceof Date && value.getTime() !== 0 && Number.isFinite(value.getTime());
}
function createLazyIterable(keys, getValue) {
  return {
    map(callback) {
      return Array.from(this, (value) => callback(value));
    },
    [Symbol.iterator]() {
      let index = 0;
      const iterator = {
        next() {
          if (index >= keys.length) return {
            value: void 0,
            done: true
          };
          return {
            value: getValue(keys[index++]),
            done: false
          };
        },
        [Symbol.iterator]() {
          return iterator;
        }
      };
      return iterator;
    }
  };
}
function runMiddlewares(handlers, context, terminal) {
  if (handlers.length === 0) {
    terminal(context);
    return;
  }
  let index = -1;
  const dispatch = (nextIndex) => {
    if (nextIndex <= index) throw new Error("Middleware next() called multiple times");
    index = nextIndex;
    if (nextIndex >= handlers.length) {
      terminal(context);
      return;
    }
    const handler = handlers[nextIndex];
    if (!handler) {
      dispatch(nextIndex + 1);
      return;
    }
    handler(context, () => dispatch(nextIndex + 1));
  };
  dispatch(0);
}
var emptyRecordPrototype, SRSSchemaError, emptyObjectSchema, numberSchema, dateSchema, desiredRetentionSchema, elapsedDaysSchema, scheduledDaysSchema, fractionalDaysConfigSchema;
var init_schema_CgTDED3c = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/schema-CgTDED3c.js"() {
    emptyRecordPrototype = Object.freeze(/* @__PURE__ */ Object.create(null));
    SRSSchemaError = class SRSSchemaError2 extends Error {
      issues;
      constructor(issues) {
        super(issues.map((issue) => issue.message).join("\n"));
        this.name = "SRSSchemaError";
        this.issues = issues;
        Error?.captureStackTrace?.(this, SRSSchemaError2);
      }
    };
    emptyObjectSchema = defineSchema((value) => {
      if (!isObject2(value) || Object.keys(value).length > 0) return { issues: [{ message: "Expected empty object" }] };
      return { value: {} };
    });
    numberSchema = defineSchema((value) => isFiniteNumber(value) ? { value } : { issues: [{ message: "Expected finite number" }] });
    dateSchema = defineSchema((value) => isValidDate(value) ? { value } : { issues: [{ message: "Expected valid Date" }] });
    desiredRetentionSchema = defineSchema((value) => isFiniteNumber(value) && value > 0 && value < 1 ? { value } : { issues: [{ message: "desiredRetention must be finite and in (0, 1)" }] });
    elapsedDaysSchema = defineSchema((value) => isFiniteNumber(value) && value >= 0 ? { value } : { issues: [{ message: "elapsedDays must be finite and non-negative" }] });
    scheduledDaysSchema = defineSchema((value) => isFiniteNumber(value) && value >= 0 ? { value } : { issues: [{ message: "scheduledDays must be finite and non-negative" }] });
    fractionalDaysConfigSchema = defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected fractional days config" }] };
      const fractionalDays = value.fractionalDays === void 0 ? false : value.fractionalDays;
      if (typeof fractionalDays !== "boolean") return { issues: [{ message: "Expected fractionalDays to be a boolean" }] };
      return { value: { fractionalDays } };
    });
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/define-chrono-DVqT65EB.js
function defineChronoTimeNormalizer(validate) {
  return defineSchema(validate);
}
function resolveChronoTimeNormalizer(normalize) {
  if (typeof normalize === "function") return defineChronoTimeNormalizer(normalize);
  return normalize;
}
function defineChrono(definition) {
  return {
    schema: {
      time: definition.schema.time,
      ...definition.schema.config ? { config: definition.schema.config } : {},
      ...definition.schema.card ? { card: definition.schema.card } : {},
      ...definition.schema.revlog ? { revlog: definition.schema.revlog } : {}
    },
    normalize: resolveChronoTimeNormalizer(definition.normalize),
    defaultValue: definition.defaultValue ?? {},
    create: definition.create
  };
}
var init_define_chrono_DVqT65EB = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/define-chrono-DVqT65EB.js"() {
    init_schema_CgTDED3c();
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/state-B8lS4k1a.js
var Rating, ratings, grades, ratingSchema, gradeSchema, State, states, stateSchema;
var init_state_B8lS4k1a = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/state-B8lS4k1a.js"() {
    init_schema_CgTDED3c();
    Rating = Object.freeze({
      Manual: 0,
      Again: 1,
      Hard: 2,
      Good: 3,
      Easy: 4
    });
    ratings = Object.freeze([
      Rating.Manual,
      Rating.Again,
      Rating.Hard,
      Rating.Good,
      Rating.Easy
    ]);
    grades = Object.freeze([
      Rating.Again,
      Rating.Hard,
      Rating.Good,
      Rating.Easy
    ]);
    ratingSchema = defineSchema((value) => value === Rating.Manual || value === Rating.Again || value === Rating.Hard || value === Rating.Good || value === Rating.Easy ? { value } : { issues: [{ message: "Expected rating" }] });
    gradeSchema = defineSchema((value) => value === Rating.Again || value === Rating.Hard || value === Rating.Good || value === Rating.Easy ? { value } : { issues: [{ message: "Expected grade" }] });
    State = Object.freeze({
      New: 0,
      Learning: 1,
      Review: 2,
      Relearning: 3
    });
    states = Object.freeze([
      State.New,
      State.Learning,
      State.Review,
      State.Relearning
    ]);
    stateSchema = defineSchema((value) => value === State.New || value === State.Learning || value === State.Review || value === State.Relearning ? { value } : { issues: [{ message: "Expected state" }] });
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/middleware-CkL5v5zL.js
function defineMiddleware(definition) {
  return definition;
}
var statsConfigSchema, statsFieldsSchema, schedulerStatsMiddleware;
var init_middleware_CkL5v5zL = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/middleware-CkL5v5zL.js"() {
    init_schema_CgTDED3c();
    init_state_B8lS4k1a();
    statsConfigSchema = defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected stats config object" }] };
      const { clearStatsOnForget } = value;
      if (clearStatsOnForget === void 0) return { value: { clearStatsOnForget: true } };
      if (typeof clearStatsOnForget !== "boolean") return { issues: [{ message: "Expected boolean clearStatsOnForget" }] };
      return { value: { clearStatsOnForget } };
    });
    statsFieldsSchema = defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected stats object" }] };
      const { reps, lapses } = value;
      if (typeof reps !== "number" || !Number.isSafeInteger(reps) || reps < 0) return { issues: [{ message: "Expected non-negative integer reps" }] };
      if (typeof lapses !== "number" || !Number.isSafeInteger(lapses) || lapses < 0) return { issues: [{ message: "Expected non-negative integer lapses" }] };
      return { value: {
        reps,
        lapses
      } };
    });
    schedulerStatsMiddleware = defineMiddleware({
      name: Symbol("srs-kit.stats"),
      schema: {
        config: statsConfigSchema,
        card: statsFieldsSchema
      },
      defaultValue: { card(ctx) {
        if (ctx.operation === "forget" && ctx.config.clearStatsOnForget === false) {
          const card = ctx.input;
          return {
            reps: card.reps,
            lapses: card.lapses
          };
        }
        return {
          reps: 0,
          lapses: 0
        };
      } },
      handlers: {
        review(ctx, next) {
          next();
          const card = ctx.input.card;
          const previousState = card.state;
          const previousLapses = card.lapses;
          const isLapse = ctx.input.grade === Rating.Again && previousState === State.Review;
          ctx.result.card.reps = card.reps + 1;
          ctx.result.card.lapses = isLapse ? previousLapses + 1 : previousLapses;
        },
        rollback(ctx, next) {
          next();
          const card = ctx.input.card;
          const revlog = ctx.input.revlog;
          const isLapse = revlog.rating === Rating.Again && revlog.state === State.Review;
          ctx.result.card.reps = Math.max(0, card.reps - 1);
          ctx.result.card.lapses = Math.max(0, card.lapses - (isLapse ? 1 : 0));
        }
      }
    });
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/model/index.js
function defineModel(definition) {
  return definition;
}
var init_model = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/model/index.js"() {
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/status-Bx46bpYh.js
var scheduleStatuses, scheduleStatusSchema;
var init_status_Bx46bpYh = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/status-Bx46bpYh.js"() {
    init_schema_CgTDED3c();
    scheduleStatuses = Object.freeze([
      "new",
      "learning",
      "review"
    ]);
    scheduleStatusSchema = defineSchema((value) => value === "new" || value === "learning" || value === "review" ? { value } : { issues: [{ message: "Expected schedule status" }] });
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/scheduler-BnkL-8NY.js
function getAttachedValue(target, key) {
  return target[key];
}
function rememberAttachedValue(target, key, value) {
  Object.defineProperty(target, key, {
    value,
    writable: false,
    enumerable: false,
    configurable: false
  });
  return target;
}
function createSchedulerSchema(ctx) {
  const { model, chrono, middlewares } = ctx;
  const modelConfigSchema = model.schema.config;
  const chronoSchema = chrono.schema;
  const chronoConfigSchema = chronoSchema.config;
  const chronoCardSchema = chronoSchema.card;
  const chronoRevlogSchema = chronoSchema.revlog;
  const middlewareConfigSchemas = [];
  const middlewareCardInitInputSchemas = [];
  const middlewareCardSchemas = [];
  const middlewareRevlogSchemas = [];
  for (const middleware of middlewares) {
    const schema = middleware.schema;
    if (!schema) continue;
    if (schema.config) middlewareConfigSchemas.push(schema.config);
    if (schema.cardInitInput) middlewareCardInitInputSchemas.push(schema.cardInitInput);
    if (schema.card) middlewareCardSchemas.push(schema.card);
    if (schema.revlog) middlewareRevlogSchemas.push(schema.revlog);
  }
  const scheduleStatusSchema2 = defineSchema((value) => {
    if (typeof value !== "string") return { issues: [{ message: "Expected scheduleStatus string" }] };
    let isKnownStatus = scheduleStatuses.includes(value);
    for (const middleware of middlewares) {
      if (isKnownStatus) break;
      isKnownStatus = middleware.scheduleStatus?.includes(value) === true;
    }
    if (!isKnownStatus) return { issues: [{ message: "Expected known scheduleStatus" }] };
    return { value };
  });
  const parseCoreFields = (fields, options) => {
    const scheduleStatus = validateSync(scheduleStatusSchema2, fields.scheduleStatus);
    if (scheduleStatus.issues) return scheduleStatus;
    const state = validateSync(stateSchema, fields.state);
    if (state.issues) return state;
    if (!options?.rating) return { value: {
      state: state.value,
      scheduleStatus: scheduleStatus.value
    } };
    const rating = validateSync(gradeSchema, fields.rating);
    if (rating.issues) return rating;
    return { value: {
      state: state.value,
      scheduleStatus: scheduleStatus.value,
      rating: rating.value
    } };
  };
  return {
    config: defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected scheduler config object" }] };
      const modelResult = validateSync(modelConfigSchema, value);
      if (modelResult.issues) return modelResult;
      const result = {};
      assignObjectFields(result, modelResult.value);
      if (chronoConfigSchema) {
        const chronoResult = validateSync(chronoConfigSchema, value);
        if (chronoResult.issues) return chronoResult;
        assignObjectFields(result, chronoResult.value);
      }
      for (const schema of middlewareConfigSchemas) {
        const middlewareResult = validateSync(schema, value);
        if (middlewareResult.issues) return middlewareResult;
        assignObjectFields(result, middlewareResult.value);
      }
      return { value: rememberAttachedValue(result, parsedModelConfigSymbol, modelResult.value) };
    }),
    cardInitInput: defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected card init input object" }] };
      const { now: now4, ...middlewareValue } = value;
      let firstMiddlewareFields;
      let combinedFields;
      for (const schema of middlewareCardInitInputSchemas) {
        const middlewareResult = validateSync(schema, middlewareValue);
        if (middlewareResult.issues) return middlewareResult;
        const fields = middlewareResult.value;
        if (firstMiddlewareFields === void 0) {
          firstMiddlewareFields = fields;
          continue;
        }
        combinedFields ??= { ...firstMiddlewareFields };
        assignObjectFields(combinedFields, fields);
      }
      return { value: {
        input: combinedFields ?? firstMiddlewareFields ?? {},
        now: now4
      } };
    }),
    card: defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected card object" }] };
      const modelResult = validateSync(model.schema.memoryState, value);
      if (modelResult.issues) return modelResult;
      const memoryState = modelResult.value;
      const card = { ...memoryState };
      if (chronoCardSchema) {
        const chronoCard = validateSync(chronoCardSchema, value);
        if (chronoCard.issues) return chronoCard;
        assignEnumerableDataFields(card, chronoCard.value);
      }
      const coreFields = parseCoreFields(value);
      if (coreFields.issues) return coreFields;
      card.state = coreFields.value.state;
      card.scheduleStatus = coreFields.value.scheduleStatus;
      for (const schema of middlewareCardSchemas) {
        const middlewareCard = validateSync(schema, value);
        if (middlewareCard.issues) return middlewareCard;
        assignEnumerableDataFields(card, middlewareCard.value);
      }
      return { value: rememberAttachedValue(card, parsedCardMemoryStateSymbol, memoryState) };
    }),
    revlog: defineSchema((value) => {
      if (!isObject2(value)) return { issues: [{ message: "Expected revlog object" }] };
      const modelResult = validateSync(model.schema.memoryState, value);
      if (modelResult.issues) return modelResult;
      const result = modelResult.value;
      if (chronoRevlogSchema) {
        const chronoRevlog = validateSync(chronoRevlogSchema, value);
        if (chronoRevlog.issues) return chronoRevlog;
        assignEnumerableDataFields(result, chronoRevlog.value);
      }
      const coreFields = parseCoreFields(value, { rating: true });
      if (coreFields.issues) return coreFields;
      result.scheduleStatus = coreFields.value.scheduleStatus;
      result.rating = coreFields.value.rating;
      result.state = coreFields.value.state;
      for (const schema of middlewareRevlogSchemas) {
        const middlewareRevlog = validateSync(schema, value);
        if (middlewareRevlog.issues) return middlewareRevlog;
        assignEnumerableDataFields(result, middlewareRevlog.value);
      }
      return { value: result };
    }),
    scheduleStatus: scheduleStatusSchema2
  };
}
function resolveChronoDefault(value) {
  return isFunction(value) ? value : void 0;
}
function createSchedulerDefaultValue(ctx) {
  const { model, chrono, middlewares } = ctx;
  const chronoCardDefault = resolveChronoDefault(chrono.defaultValue?.card);
  const cardDefaults = middlewares.map((middleware) => middleware.defaultValue?.card).filter(isFunction);
  return { newCard(defaultValue, time) {
    const { config } = defaultValue;
    const card = Object.assign(Object.create(emptyRecordPrototype), model.defaultValue.memoryState({ config }));
    card.state = State.New;
    card.scheduleStatus = "new";
    if (chronoCardDefault) Object.assign(card, chronoCardDefault({
      config,
      time,
      previous: null
    }));
    for (const getDefaults of cardDefaults) Object.assign(card, getDefaults(defaultValue));
    return Object.setPrototypeOf(card, Object.prototype);
  } };
}
function flattenMiddlewares(node) {
  if (!node) return emptyMiddlewares;
  const middlewares = new Array(node.length);
  let index = node.length;
  for (let current = node; current; current = current.parent) middlewares[--index] = current.middleware;
  return middlewares;
}
function defineScheduler(definition) {
  const { model, chrono } = definition;
  function build(node) {
    let middlewares;
    let defaultValue;
    let schedulerSchema;
    let initialized = false;
    const getMiddlewares = () => {
      middlewares ??= flattenMiddlewares(node);
      return middlewares;
    };
    const scheduler = {
      name: model.name,
      modelDef: model,
      chronoDef: chrono,
      get defaultValue() {
        defaultValue ??= createSchedulerDefaultValue({
          model,
          chrono,
          middlewares: getMiddlewares()
        });
        return defaultValue;
      },
      get schema() {
        schedulerSchema ??= createSchedulerSchema({
          model,
          chrono,
          middlewares: getMiddlewares()
        });
        return schedulerSchema;
      },
      create(ctx) {
        if (!initialized) {
          schedulerSchema = scheduler.schema;
          defaultValue = scheduler.defaultValue;
          initialized = true;
        }
        return new BaseScheduler({
          model,
          chrono,
          schema: schedulerSchema,
          defaultValue,
          middlewares,
          config: ctx.config
        });
      },
      use(...added) {
        if (added.length === 0) return scheduler;
        let child = node;
        let length = node?.length ?? 0;
        for (const middleware of added) child = {
          parent: child,
          middleware,
          length: ++length
        };
        return build(child);
      }
    };
    return scheduler;
  }
  return build();
}
var parsedModelConfigSymbol, parsedCardMemoryStateSymbol, DEFAULT_DESIRED_RETENTION, FORWARD_PREPARE_OPTIONS, ReviewInput, BaseScheduler, emptyMiddlewares;
var init_scheduler_BnkL_8NY = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/scheduler-BnkL-8NY.js"() {
    init_schema_CgTDED3c();
    init_state_B8lS4k1a();
    init_status_Bx46bpYh();
    parsedModelConfigSymbol = Symbol("parsedModelConfig");
    parsedCardMemoryStateSymbol = Symbol("parsedCardMemoryState");
    DEFAULT_DESIRED_RETENTION = 0.9;
    FORWARD_PREPARE_OPTIONS = { freezeCard: false };
    ReviewInput = class {
      input;
      constructor(input) {
        this.input = input;
      }
      get card() {
        return this.input.card;
      }
      set card(_value) {
        throw new Error("Review input card cannot be changed");
      }
      get grade() {
        return this.input.grade;
      }
      set grade(_value) {
        throw new Error("Review input grade cannot be changed");
      }
      get now() {
        return this.input.now;
      }
      set now(_value) {
        throw new Error("Review input now cannot be changed");
      }
    };
    BaseScheduler = class {
      config;
      model;
      chrono;
      schedulerDefinition;
      defaultValue;
      schema;
      nextIntervalHandlers;
      reviewHandlers;
      reviewIntervalHandlers;
      rollbackHandlers;
      constructor(ctx) {
        const { model, chrono, schema, defaultValue, middlewares = [] } = ctx;
        this.schedulerDefinition = Object.freeze({
          model,
          chrono
        });
        this.schema = schema;
        this.defaultValue = defaultValue;
        const config = parse(schema.config, ctx.config);
        this.config = config;
        this.model = model.create({
          config: getAttachedValue(config, parsedModelConfigSymbol),
          bypass: true
        });
        this.chrono = Reflect.apply(chrono.create, chrono, [{ config }]);
        this.nextIntervalHandlers = middlewares.map((middleware) => middleware.handlers?.nextInterval);
        this.reviewHandlers = middlewares.map((middleware) => middleware.handlers?.review);
        this.reviewIntervalHandlers = this.reviewHandlers.flatMap((handler, index) => [handler, this.nextIntervalHandlers[index]]);
        this.rollbackHandlers = middlewares.map((middleware) => middleware.handlers?.rollback);
      }
      get definition() {
        return this.schedulerDefinition;
      }
      createNewCard = (options) => {
        const { now: now4, input } = parse(this.schema.cardInitInput, options === void 0 ? {} : options);
        return this.defaultValue.newCard({
          operation: "newCard",
          config: this.config,
          input
        }, this.parseNow(now4));
      };
      newCard = this.createNewCard;
      /**
      * Replays a review history and returns the card and revlog produced by each
      * review.
      *
      * The history is consumed as given: it must already be sorted by review time
      * and must not contain manual ratings.
      */
      forward = (input) => {
        const { history } = input;
        if (history.length === 0) return [];
        const results = new Array(history.length);
        const initialCard = input.initialCard == null ? this.createNewCard({ now: history[0].reviewTime }) : input.initialCard;
        let card = parse(this.schema.card, initialCard);
        for (let index = 0; index < history.length; index++) {
          const review = history[index];
          const now4 = review.reviewTime;
          const prepared = this.prepareParsedReview(card, now4, FORWARD_PREPARE_OPTIONS);
          const result = this.parseReviewResult(this.runReview(prepared, review.rating, now4));
          results[index] = result;
          card = result.card;
        }
        return results;
      };
      forget = (input) => {
        const card = parse(this.schema.card, input.card);
        const now4 = this.parseNow(input.now);
        return this.defaultValue.newCard({
          operation: "forget",
          config: this.config,
          input: card
        }, now4);
      };
      nextInterval = (memoryState, desiredRetention, context) => {
        const grade = parse(gradeSchema, context.grade);
        const elapsedDays = parse(elapsedDaysSchema, context.elapsedDays);
        const retention = parse(desiredRetentionSchema, desiredRetention);
        const card = Object.freeze(parse(this.schema.card, context.card));
        const _memoryState = getAttachedValue(card, parsedCardMemoryStateSymbol);
        if (!_memoryState) throw new Error("Parsed scheduler card is missing model memory state");
        const nextMemoryState = parse(this.schedulerDefinition.model.schema.memoryState, memoryState);
        const candidate = this.createCandidate(_memoryState, elapsedDays, void 0, [grade, nextMemoryState], retention);
        const ctx = {
          instance: this,
          config: this.config,
          input: Object.freeze({
            card,
            grade,
            desiredRetention: retention
          }),
          elapsedDays,
          scheduledDays: void 0,
          candidate
        };
        runMiddlewares(this.nextIntervalHandlers, ctx, (ctx2) => {
          const memoryState2 = ctx2.candidate.step(ctx2.input.grade);
          ctx2.scheduledDays ??= ctx2.candidate.nextInterval(memoryState2, parse(desiredRetentionSchema, ctx2.candidate.desiredRetention[ctx2.input.grade]));
        });
        return parse(scheduledDaysSchema, ctx.scheduledDays);
      };
      review = (input) => {
        const { card: inputCard, grade: inputGrade } = input;
        const grade = parse(gradeSchema, inputGrade);
        const now4 = this.parseNow(input.now);
        const prepared = this.prepareReview(inputCard, now4);
        return this.parseReviewResult(this.runReview(prepared, grade, now4));
      };
      preview = (input) => {
        const inputCard = input.card;
        const now4 = this.parseNow(input.now);
        const prepared = this.prepareReview(inputCard, now4);
        return createLazyIterable(grades, (grade) => {
          const { card, revlog } = this.parseReviewResult(this.runReview(prepared, grade, now4));
          return {
            grade,
            card,
            revlog
          };
        });
      };
      rollback = (input) => {
        const { card: inputCard, revlog: inputRevlog } = input;
        const revlog = parse(this.schema.revlog, inputRevlog);
        const card = parse(this.schema.card, inputCard);
        const ctx = {
          instance: this,
          config: this.config,
          input: {
            card: Object.freeze(card),
            revlog: Object.freeze(revlog)
          },
          result: { card: {} }
        };
        runMiddlewares(this.rollbackHandlers, ctx, (ctx2) => this.finalizeRollback(ctx2));
        this.applyRollbackChronoDefaults(ctx.result, revlog);
        return parse(this.schema.card, ctx.result.card);
      };
      prepareReview(inputCard, now4) {
        const parsedCard = parse(this.schema.card, inputCard);
        return this.prepareParsedReview(parsedCard, now4);
      }
      prepareParsedReview(parsedCard, now4, { freezeCard = true } = {}) {
        const memoryState = getAttachedValue(parsedCard, parsedCardMemoryStateSymbol);
        if (!memoryState) throw new Error("Parsed scheduler card is missing model memory state");
        const card = freezeCard ? Object.freeze(parsedCard) : parsedCard;
        const time = parse(this.schedulerDefinition.chrono.normalize, {
          card,
          time: now4
        });
        const _elapsedDays = card.state === State.New ? 0 : this.chrono.difference(time.previous ?? time.current, now4);
        const elapsedDays = elapsedDaysSchema.parse(_elapsedDays);
        const retrievability = this.model.forgettingCurve(memoryState, elapsedDays);
        return {
          card,
          time,
          elapsedDays,
          memoryState,
          retrievability,
          candidate: this.createCandidate(memoryState, elapsedDays, retrievability)
        };
      }
      createCandidate(memoryState, elapsedDays, retrievability, initial, desiredRetention = DEFAULT_DESIRED_RETENTION) {
        const memoryStateByGrade = new Map(initial ? [initial] : void 0);
        const gradeByMemoryState = /* @__PURE__ */ new Map();
        const step = (grade) => {
          let nextMemoryState = memoryStateByGrade.get(grade);
          if (nextMemoryState === void 0) {
            retrievability ??= this.model.forgettingCurve(memoryState, elapsedDays);
            nextMemoryState = this.model.step({
              memoryState,
              rating: grade,
              elapsedDays,
              retrievability
            });
            memoryStateByGrade.set(grade, nextMemoryState);
          }
          gradeByMemoryState.set(nextMemoryState, grade);
          return nextMemoryState;
        };
        const findGrade = (nextMemoryState) => gradeByMemoryState.get(nextMemoryState);
        const intervalCache = /* @__PURE__ */ new Map();
        const nextInterval = (nextMemoryState, desiredRetention2) => {
          let inner = intervalCache.get(nextMemoryState);
          if (inner) {
            const cached = inner.get(desiredRetention2);
            if (cached !== void 0) return cached;
          } else {
            inner = /* @__PURE__ */ new Map();
            intervalCache.set(nextMemoryState, inner);
          }
          const value = this.model.nextInterval(nextMemoryState, desiredRetention2);
          inner.set(desiredRetention2, value);
          return value;
        };
        return {
          desiredRetention: {
            [Rating.Again]: desiredRetention,
            [Rating.Hard]: desiredRetention,
            [Rating.Good]: desiredRetention,
            [Rating.Easy]: desiredRetention
          },
          step,
          findGrade,
          nextInterval
        };
      }
      runReview(prepared, grade, now4) {
        const ctx = {
          instance: this,
          config: this.config,
          input: new ReviewInput({
            card: prepared.card,
            grade,
            now: now4
          }),
          elapsedDays: prepared.elapsedDays,
          retrievability: prepared.retrievability,
          scheduledDays: void 0,
          candidate: prepared.candidate,
          result: {
            card: {},
            revlog: {}
          }
        };
        runMiddlewares(this.reviewIntervalHandlers, ctx, (ctx2) => {
          const memoryState = ctx2.candidate.step(ctx2.input.grade);
          ctx2.scheduledDays ??= ctx2.candidate.nextInterval(memoryState, parse(desiredRetentionSchema, ctx2.candidate.desiredRetention[ctx2.input.grade]));
          this.finalizeReview(prepared, ctx2, memoryState);
        });
        this.applyReviewChronoDefaults(prepared, ctx);
        return ctx.result;
      }
      parseReviewResult(result) {
        return {
          card: parse(this.schema.card, result.card),
          revlog: parse(this.schema.revlog, result.revlog)
        };
      }
      finalizeReview(prepared, ctx, newMemoryState) {
        const { memoryState } = prepared;
        const { grade } = ctx.input;
        const result = ctx.result;
        assignEnumerableDataFields(result.card, newMemoryState, {
          state: State.Review,
          scheduleStatus: "review"
        });
        assignEnumerableDataFields(result.revlog, memoryState, {
          rating: grade,
          state: prepared.card.state,
          scheduleStatus: prepared.card.scheduleStatus
        });
        return result;
      }
      finalizeRollback(ctx) {
        const result = ctx.result;
        const revlog = ctx.input.revlog;
        assignEnumerableDataFields(result.card, parse(this.schedulerDefinition.model.schema.memoryState, revlog));
        result.card.state = revlog.state;
        result.card.scheduleStatus = revlog.scheduleStatus;
        return result.card;
      }
      applyReviewChronoDefaults(prepared, ctx) {
        const { result, scheduledDays, input: { now: now4 } } = ctx;
        if (scheduledDays === void 0) throw new Error("Expected scheduledDays after review middleware");
        const chronoCardDefault = this.schedulerDefinition.chrono.defaultValue?.card;
        if (chronoCardDefault) assignEnumerableDataFields(result.card, chronoCardDefault({
          config: this.config,
          time: this.chrono.add(now4, scheduledDays),
          previous: now4
        }));
        const chronoRevlogDefault = this.schedulerDefinition.chrono.defaultValue?.revlog;
        if (chronoRevlogDefault) assignEnumerableDataFields(result.revlog, chronoRevlogDefault({
          config: this.config,
          time: prepared.time.current,
          previous: {
            previous: prepared.time.previous,
            current: now4
          }
        }));
      }
      applyRollbackChronoDefaults(result, revlog) {
        if (!this.schedulerDefinition.chrono.schema.card) return;
        const normalizedTime = parse(this.schedulerDefinition.chrono.normalize, { revlog });
        const isNew = revlog.state === State.New;
        const cardFields = this.schedulerDefinition.chrono.defaultValue?.card?.({
          config: this.config,
          previous: isNew ? null : normalizedTime.previous,
          time: normalizedTime.current
        });
        if (cardFields) assignEnumerableDataFields(result.card, cardFields);
      }
      parseNow(now4) {
        return now4 === void 0 ? this.chrono.now() : parse(this.schedulerDefinition.chrono.schema.time, now4);
      }
    };
    emptyMiddlewares = [];
  }
});

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/index.js
var init_esm = __esm({
  "node_modules/@open-spaced-repetition/srs-kit/dist/esm/index.js"() {
    init_schema_CgTDED3c();
    init_define_chrono_DVqT65EB();
    init_middleware_CkL5v5zL();
    init_state_B8lS4k1a();
    init_model();
    init_scheduler_BnkL_8NY();
  }
});

// node_modules/ts-fsrs/dist/schema-D7q2J7dh.mjs
var FSRSMemoryStateSchema;
var init_schema_D7q2J7dh = __esm({
  "node_modules/ts-fsrs/dist/schema-D7q2J7dh.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_esm();
    FSRSMemoryStateSchema = defineSchema((value) => {
      if (isObject(value) && isFiniteNumber(value.stability) && isFiniteNumber(value.difficulty)) return { value: {
        stability: value.stability,
        difficulty: value.difficulty
      } };
      return { issues: [{ message: "Expected FSRS memory state" }] };
    });
  }
});

// node_modules/ts-fsrs/dist/error.mjs
var FSRSError, FSRSValidationError;
var init_error = __esm({
  "node_modules/ts-fsrs/dist/error.mjs"() {
    FSRSError = class FSRSError2 extends Error {
      constructor(message = "FSRS Error") {
        super(message);
        this.name = "FSRSError";
        Error.captureStackTrace?.(this, FSRSError2);
      }
    };
    FSRSValidationError = class FSRSValidationError2 extends FSRSError {
      constructor(message) {
        super(message);
        this.name = "FSRSValidationError";
        Error.captureStackTrace?.(this, FSRSValidationError2);
      }
    };
  }
});

// node_modules/ts-fsrs/dist/constants-YU7EeO-L.mjs
var FSRS5_DECAY, FSRS5_FACTOR, FSRS5_W17_W18_CEILING, FSRS5_MODEL_BOUNDS, FSRS5_DEFAULT_WEIGHTS, FSRS5ParameterBounds;
var init_constants_YU7EeO_L = __esm({
  "node_modules/ts-fsrs/dist/constants-YU7EeO-L.mjs"() {
    FSRS5_DECAY = 0.5;
    FSRS5_FACTOR = 19 / 81;
    FSRS5_W17_W18_CEILING = 2;
    FSRS5_MODEL_BOUNDS = Object.freeze({
      sMin: 0.01,
      sMax: 36500,
      dMin: 1,
      dMax: 10
    });
    FSRS5_DEFAULT_WEIGHTS = Object.freeze([
      0.40255,
      1.18385,
      3.173,
      15.69105,
      7.1949,
      0.5345,
      1.4604,
      46e-4,
      1.54575,
      0.1192,
      1.01925,
      1.9395,
      0.11,
      0.29605,
      2.2698,
      0.2315,
      2.9898,
      0.51655,
      0.6621
    ]);
    FSRS5ParameterBounds = () => [
      [FSRS5_MODEL_BOUNDS.sMin, 100],
      [FSRS5_MODEL_BOUNDS.sMin, 100],
      [FSRS5_MODEL_BOUNDS.sMin, 100],
      [FSRS5_MODEL_BOUNDS.sMin, 100],
      [FSRS5_MODEL_BOUNDS.dMin, FSRS5_MODEL_BOUNDS.dMax],
      [1e-3, 4],
      [1e-3, 4],
      [1e-3, 0.75],
      [0, 4.5],
      [0, 0.8],
      [1e-3, 3.5],
      [1e-3, 5],
      [1e-3, 0.25],
      [1e-3, 0.9],
      [0, 4],
      [0, 1],
      [1, 6],
      [0, 2],
      [0, 2]
    ];
  }
});

// node_modules/ts-fsrs/dist/fsrs-6-Bt0f3F6X.mjs
function forgetting_curve(decayOrParams, elapsed_days, stability) {
  const { decay, factor } = computeDecayFactor(decayOrParams);
  return roundTo(Math.pow(1 + factor * elapsed_days / stability, decay), 8);
}
var FSRS6_DECAY, FSRS6_W17_W18_CEILING, FSRS6_MODEL_BOUNDS, FSRS6_DEFAULT_WEIGHTS, FSRS6ParameterBounds, decaySchema, clipFSRS6Parameters, checkFSRS6Parameters, migrateFSRS6Parameters, fsrs6ConfigSchema, computeDecayFactor, FSRS6Algorithm, createFSRS6Model, FSRS6Model;
var init_fsrs_6_Bt0f3F6X = __esm({
  "node_modules/ts-fsrs/dist/fsrs-6-Bt0f3F6X.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_schema_D7q2J7dh();
    init_error();
    init_constants_YU7EeO_L();
    init_esm();
    FSRS6_DECAY = 0.1542;
    FSRS6_W17_W18_CEILING = 2;
    FSRS6_MODEL_BOUNDS = Object.freeze({
      sMin: 1e-3,
      sMax: 36500,
      dMin: 1,
      dMax: 10
    });
    FSRS6_DEFAULT_WEIGHTS = Object.freeze([
      0.212,
      1.2931,
      2.3065,
      8.2956,
      6.4133,
      0.8334,
      3.0194,
      1e-3,
      1.8722,
      0.1666,
      0.796,
      1.4835,
      0.0614,
      0.2629,
      1.6483,
      0.6014,
      1.8729,
      0.5425,
      0.0912,
      0.0658,
      FSRS6_DECAY
    ]);
    FSRS6ParameterBounds = (w17W18Ceiling, enableShortTerm = true) => [
      [FSRS6_MODEL_BOUNDS.sMin, 100],
      [FSRS6_MODEL_BOUNDS.sMin, 100],
      [FSRS6_MODEL_BOUNDS.sMin, 100],
      [FSRS6_MODEL_BOUNDS.sMin, 100],
      [FSRS6_MODEL_BOUNDS.dMin, FSRS6_MODEL_BOUNDS.dMax],
      [1e-3, 4],
      [1e-3, 4],
      [1e-3, 0.75],
      [0, 4.5],
      [0, 0.8],
      [1e-3, 3.5],
      [1e-3, 5],
      [1e-3, 0.25],
      [1e-3, 0.9],
      [0, 4],
      [0, 1],
      [1, 6],
      [0, w17W18Ceiling],
      [0, w17W18Ceiling],
      [enableShortTerm ? 0.01 : 0, 0.8],
      [0.1, 0.8]
    ];
    decaySchema = defineSchema((value) => typeof value === "number" && value >= 0.1 && value <= 0.8 ? { value } : { issues: [{ message: "Expected decay between 0.1 and 0.8" }] });
    clipFSRS6Parameters = (parameters, numRelearningSteps = 0, enableShortTerm = true) => {
      const clip = FSRS6ParameterBounds(2, enableShortTerm).slice(0, parameters.length);
      if (Math.max(0, numRelearningSteps) > 1 && parameters.length >= 19) {
        const w11 = clamp(parameters[11] || 0, clip[11][0], clip[11][1]);
        const w13 = clamp(parameters[13] || 0, clip[13][0], clip[13][1]);
        const w14 = clamp(parameters[14] || 0, clip[14][0], clip[14][1]);
        const value = -(Math.log(w11) + Math.log(Math.pow(2, w13) - 1) + w14 * 0.3) / numRelearningSteps;
        const w17W18Ceiling = clamp(roundTo(Math.sqrt(Math.max(value, 0)), 8), 0.01, 2);
        clip[17] = [clip[17][0], w17W18Ceiling];
        clip[18] = [clip[18][0], w17W18Ceiling];
      }
      return clip.map(([min, max], index) => clamp(parameters[index] || 0, min, max));
    };
    checkFSRS6Parameters = (parameters, numRelearningSteps = 0, enableShortTerm = true) => {
      const clipped = clipFSRS6Parameters(Array.from(parameters), numRelearningSteps, enableShortTerm);
      if (!(parameters.length === FSRS6_DEFAULT_WEIGHTS.length && clipped.every((value, index) => value === parameters[index]))) throw new FSRSValidationError("Expected FSRS6 weights within model bounds.");
      return parameters;
    };
    migrateFSRS6Parameters = (parameters) => {
      if (!Array.isArray(parameters) || parameters.length === 0) return [...FSRS6_DEFAULT_WEIGHTS];
      switch (parameters.length) {
        case 21:
          return Array.from(parameters);
        case 19:
          return Array.from(parameters).concat([0, FSRS5_DECAY]);
        case 17: {
          const weights = Array.from(parameters);
          weights[4] = +(weights[5] * 2 + weights[4]).toFixed(8);
          weights[5] = +(Math.log(weights[5] * 3 + 1) / 3).toFixed(8);
          weights[6] = +(weights[6] + 0.5).toFixed(8);
          return weights.concat([
            0,
            0,
            0,
            FSRS5_DECAY
          ]);
        }
        default:
          throw new FSRSValidationError(`Invalid parameters length "${parameters.length}", expected 17, 19 or 21.`);
      }
    };
    fsrs6ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights) && typeof value.enableShortTerm === "boolean" && typeof value.numRelearningSteps === "number" && Number.isSafeInteger(value.numRelearningSteps) && value.numRelearningSteps >= 0) return { value: {
        weights: value.weights,
        enableShortTerm: value.enableShortTerm,
        numRelearningSteps: value.numRelearningSteps
      } };
      return { issues: [{ message: "Expected FSRS6 config" }] };
    });
    computeDecayFactor = (decayOrParams) => {
      const decay = typeof decayOrParams === "number" ? -decayOrParams : -decayOrParams[20];
      const factor = Math.exp(Math.pow(decay, -1) * Math.log(0.9)) - 1;
      return {
        decay,
        factor: roundTo(factor, 8)
      };
    };
    FSRS6Algorithm = class {
      weights;
      enableShortTerm;
      bounds;
      decayWeight = NaN;
      decay = 0;
      factor = 0;
      forgetting_curve;
      constructor(weights, enableShortTerm, bounds) {
        this.weights = weights;
        this.enableShortTerm = enableShortTerm;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 21) throw new FSRSValidationError(`FSRS6Algorithm requires exactly 21 weights, but received ${weights?.length}`);
        this.forgetting_curve = (elapsed_days, stability) => {
          const { decay, factor } = this.getDecayFactor();
          return roundTo(Math.pow(1 + factor * elapsed_days / stability, decay), 8);
        };
      }
      getDecayFactor() {
        const decayWeight = this.weights[20];
        if (decayWeight !== this.decayWeight) {
          const { decay, factor } = computeDecayFactor(decayWeight);
          this.decayWeight = decayWeight;
          this.decay = decay;
          this.factor = factor;
        }
        return {
          decay: this.decay,
          factor: this.factor
        };
      }
      init_stability(g) {
        return clamp(this.weights[g - 1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(g) {
        const w = this.weights;
        const d = w[4] - Math.exp((g - 1) * w[5]) + 1;
        return roundTo(d, 8);
      }
      next_interval(s, desired_retention) {
        if (!Number.isFinite(desired_retention) || desired_retention <= 0 || desired_retention > 1) throw new FSRSValidationError("Desired retention rate should be in the range (0,1]");
        const { decay, factor } = this.getDecayFactor();
        return Math.max(Math.round(s / factor * (Math.pow(desired_retention, 1 / decay) - 1)), 1);
      }
      /**
      * @see https://github.com/open-spaced-repetition/fsrs4anki/issues/697
      */
      linear_damping(delta_d, old_d) {
        return roundTo(delta_d * (10 - old_d) / 9, 8);
      }
      next_difficulty(d, g) {
        const delta_d = -this.weights[6] * (g - 3);
        const next_d = d + this.linear_damping(delta_d, d);
        return clamp(this.mean_reversion(this.init_difficulty(Rating.Easy), next_d), 1, 10);
      }
      mean_reversion(init, current) {
        const w = this.weights;
        return roundTo(w[7] * init + (1 - w[7]) * current, 8);
      }
      next_recall_stability(d, s, r, g) {
        const w = this.weights;
        const hard_penalty = Rating.Hard === g ? w[15] : 1;
        const easy_bound = Rating.Easy === g ? w[16] : 1;
        return roundTo(clamp(s * (1 + Math.exp(w[8]) * (11 - d) * Math.pow(s, -w[9]) * (Math.exp((1 - r) * w[10]) - 1) * hard_penalty * easy_bound), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_forget_stability(d, s, r) {
        const w = this.weights;
        return roundTo(clamp(w[11] * Math.pow(d, -w[12]) * (Math.pow(s + 1, w[13]) - 1) * Math.exp((1 - r) * w[14]), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_short_term_stability(s, g) {
        const w = this.weights;
        const sinc = Math.pow(s, -w[19]) * Math.exp(w[17] * (g - 3 + w[18]));
        const maskedSinc = g >= Rating.Hard ? Math.max(sinc, 1) : sinc;
        return roundTo(clamp(s * maskedSinc, this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_state(memory_state, t, g, r) {
        const { difficulty: d, stability: s } = memory_state ?? {
          difficulty: 0,
          stability: 0
        };
        if (t < 0) throw new FSRSValidationError(`Invalid delta_t "${t}"`);
        if (g < 0 || g > 4) throw new FSRSValidationError(`Invalid grade "${g}"`);
        if (g === Rating.Manual) return {
          difficulty: d,
          stability: s
        };
        const grade = g;
        if (d === 0 && s === 0) return {
          difficulty: clamp(this.init_difficulty(grade), 1, 10),
          stability: this.init_stability(grade)
        };
        if (d < 1 || s < this.bounds.sMin) throw new FSRSValidationError(`Invalid memory state { difficulty: ${d}, stability: ${s} }`);
        const w = this.weights;
        r = typeof r === "number" ? r : this.forgetting_curve(t, s);
        let new_s;
        if (t === 0 && this.enableShortTerm) new_s = this.next_short_term_stability(s, grade);
        else if (g === 1) {
          const s_after_fail = this.next_forget_stability(d, s, r);
          let [w_17, w_18] = [0, 0];
          if (this.enableShortTerm) {
            w_17 = w[17];
            w_18 = w[18];
          }
          const next_s_min = s / Math.exp(w_17 * w_18);
          new_s = clamp(roundTo(next_s_min, 8), this.bounds.sMin, s_after_fail);
        } else new_s = this.next_recall_stability(d, s, r, grade);
        return {
          difficulty: this.next_difficulty(d, grade),
          stability: new_s
        };
      }
    };
    createFSRS6Model = (config) => {
      const bounds = FSRS6_MODEL_BOUNDS;
      const algo = new FSRS6Algorithm(config.weights, config.enableShortTerm, FSRS6_MODEL_BOUNDS);
      const step = ({ memoryState, rating, elapsedDays, retrievability }) => {
        return algo.next_state(memoryState, elapsedDays, rating, retrievability);
      };
      const nextInterval = (memoryState, desiredRetention) => {
        return algo.next_interval(memoryState.stability, desiredRetention);
      };
      const forgettingCurve = (memoryState, elapsedDays) => {
        return algo.forgetting_curve(elapsedDays, memoryState.stability);
      };
      const forward = ({ history, initialState }) => {
        const states2 = [];
        let memoryState = initialState || null;
        for (const review of history) {
          memoryState = step({
            memoryState,
            rating: review.rating,
            elapsedDays: review.deltaT
          });
          states2.push(memoryState);
        }
        return states2;
      };
      return {
        config,
        bounds,
        algorithm: algo,
        step,
        nextInterval,
        forgettingCurve,
        forward
      };
    };
    FSRS6Model = defineModel({
      name: "fsrs-6",
      schema: {
        config: fsrs6ConfigSchema,
        memoryState: FSRSMemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS6Model(config);
        let weights = migrate ? migrateFSRS6Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS6Parameters(weights, config.numRelearningSteps, config.enableShortTerm);
        if (check) checkFSRS6Parameters(weights, config.numRelearningSteps, config.enableShortTerm);
        const $config = fsrs6ConfigSchema.parse({
          weights,
          enableShortTerm: config.enableShortTerm,
          numRelearningSteps: config.numRelearningSteps
        });
        return createFSRS6Model(Object.freeze($config));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-3.mjs
var fsrs_3_exports = {};
__export(fsrs_3_exports, {
  FSRS3Algorithm: () => FSRS3Algorithm,
  FSRS3Model: () => FSRS3Model,
  FSRS3ParameterBounds: () => FSRS3ParameterBounds,
  FSRS3_DEFAULT_WEIGHTS: () => FSRS3_DEFAULT_WEIGHTS,
  FSRS3_MODEL_BOUNDS: () => FSRS3_MODEL_BOUNDS,
  checkFSRS3Parameters: () => checkFSRS3Parameters,
  clipFSRS3Parameters: () => clipFSRS3Parameters,
  forgettingCurve: () => forgetting_curve2,
  fsrs3ConfigSchema: () => fsrs3ConfigSchema,
  migrateFSRS3Parameters: () => migrateFSRS3Parameters
});
function forgetting_curve2(elapsed_days, stability) {
  return roundTo(Math.pow(0.9, elapsed_days / stability), 8);
}
var FSRS3Algorithm, FSRS3_MODEL_BOUNDS, FSRS3_DEFAULT_WEIGHTS, FSRS3ParameterBounds, clipFSRS3Parameters, checkFSRS3Parameters, migrateFSRS3Parameters, fsrs3ConfigSchema, createFSRS3Model, FSRS3Model;
var init_fsrs_3 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-3.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_schema_D7q2J7dh();
    init_error();
    init_esm();
    FSRS3Algorithm = class {
      weights;
      bounds;
      constructor(weights, bounds) {
        this.weights = weights;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 13) throw new FSRSValidationError(`FSRS3Algorithm requires exactly 13 weights, but received ${weights?.length}`);
      }
      init_stability(g) {
        const w = this.weights;
        return clamp(w[0] + (g - 1) * w[1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(g) {
        const w = this.weights;
        return clamp(w[2] + (g - 3) * w[3], this.bounds.dMin, this.bounds.dMax);
      }
      next_interval(s, desired_retention) {
        if (!Number.isFinite(desired_retention) || desired_retention <= 0 || desired_retention > 1) throw new FSRSValidationError("Desired retention rate should be in the range (0,1]");
        const intervalModifier = Math.log(desired_retention) / Math.log(0.9);
        return roundTo(Math.max(Math.round(s * intervalModifier), 1), 8);
      }
      next_difficulty(d, g) {
        const w = this.weights;
        const next_d = d + w[4] * (g - 3);
        return roundTo(clamp(this.mean_reversion(w[2], next_d), this.bounds.dMin, this.bounds.dMax), 8);
      }
      mean_reversion(init, current) {
        const w = this.weights;
        return roundTo(w[5] * init + (1 - w[5]) * current, 8);
      }
      next_recall_stability(d, s, r) {
        const w = this.weights;
        return roundTo(clamp(s * (1 + Math.exp(w[6]) * (11 - d) * Math.pow(s, w[7]) * (Math.exp((1 - r) * w[8]) - 1)), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_forget_stability(d, s, r) {
        const w = this.weights;
        return roundTo(clamp(w[9] * Math.pow(d, w[10]) * Math.pow(s, w[11]) * Math.exp((1 - r) * w[12]), this.bounds.sMin, this.bounds.sMax), 8);
      }
      forgetting_curve = forgetting_curve2;
      next_state(memory_state, t, g, r) {
        const { difficulty: d, stability: s } = memory_state ?? {
          difficulty: 0,
          stability: 0
        };
        if (t < 0) throw new FSRSValidationError(`Invalid delta_t "${t}"`);
        if (g < 0 || g > 4) throw new FSRSValidationError(`Invalid grade "${g}"`);
        if (g === Rating.Manual) return {
          difficulty: d,
          stability: s
        };
        const grade = g;
        if (d === 0 && s === 0) return {
          difficulty: this.init_difficulty(grade),
          stability: this.init_stability(grade)
        };
        if (d < this.bounds.dMin || s < this.bounds.sMin) throw new FSRSValidationError(`Invalid memory state { difficulty: ${d}, stability: ${s} }`);
        r = typeof r === "number" ? r : this.forgetting_curve(t, s);
        const new_d = this.next_difficulty(d, grade);
        return {
          difficulty: new_d,
          stability: grade === Rating.Again ? this.next_forget_stability(new_d, s, r) : this.next_recall_stability(new_d, s, r)
        };
      }
    };
    FSRS3_MODEL_BOUNDS = Object.freeze({
      sMin: 0.01,
      sMax: 36500,
      dMin: 1,
      dMax: 10
    });
    FSRS3_DEFAULT_WEIGHTS = Object.freeze([
      0.9605,
      1.7234,
      4.8527,
      -1.1917,
      -1.2956,
      0.0573,
      1.7352,
      -0.1673,
      1.065,
      1.8907,
      -0.3832,
      0.5867,
      1.0721
    ]);
    FSRS3ParameterBounds = () => [
      [0.1, 10],
      [0.1, 5],
      [FSRS3_MODEL_BOUNDS.dMin, FSRS3_MODEL_BOUNDS.dMax],
      [-5, -0.1],
      [-5, -0.1],
      [0.05, 0.5],
      [0, 2],
      [-0.8, -0.15],
      [0.01, 1.5],
      [0.5, 5],
      [-2, -0.01],
      [0.01, 0.9],
      [0.01, 2]
    ];
    clipFSRS3Parameters = (parameters) => {
      return FSRS3ParameterBounds().slice(0, parameters.length).map(([min, max], index) => clamp(parameters[index] ?? 0, min, max));
    };
    checkFSRS3Parameters = (parameters) => {
      const clipped = clipFSRS3Parameters(Array.from(parameters));
      if (!(parameters.length === FSRS3_DEFAULT_WEIGHTS.length && clipped.every((value, index) => value === parameters[index]))) throw new FSRSValidationError("Expected FSRS3 weights within model bounds.");
      return parameters;
    };
    migrateFSRS3Parameters = (parameters) => {
      if (!Array.isArray(parameters) || parameters.length === 0) return [...FSRS3_DEFAULT_WEIGHTS];
      return parameters.slice(0, FSRS3_DEFAULT_WEIGHTS.length);
    };
    fsrs3ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights)) return { value: { weights: value.weights } };
      return { issues: [{ message: "Expected FSRS3 config" }] };
    });
    createFSRS3Model = (config) => {
      const bounds = FSRS3_MODEL_BOUNDS;
      const algo = new FSRS3Algorithm(config.weights, bounds);
      const step = ({ memoryState, rating, elapsedDays, retrievability }) => {
        return algo.next_state(memoryState, elapsedDays, rating, retrievability);
      };
      const nextInterval = (memoryState, desiredRetention) => {
        return algo.next_interval(memoryState.stability, desiredRetention);
      };
      const forgettingCurve = (memoryState, elapsedDays) => {
        return algo.forgetting_curve(elapsedDays, memoryState.stability);
      };
      const forward = ({ history, initialState }) => {
        const states2 = [];
        let memoryState = initialState || null;
        for (const review of history) {
          memoryState = step({
            memoryState,
            rating: review.rating,
            elapsedDays: review.deltaT
          });
          states2.push(memoryState);
        }
        return states2;
      };
      return {
        config,
        bounds,
        algorithm: algo,
        step,
        nextInterval,
        forgettingCurve,
        forward
      };
    };
    FSRS3Model = defineModel({
      name: "fsrs-3",
      schema: {
        config: fsrs3ConfigSchema,
        memoryState: FSRSMemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS3Model(config);
        let weights = migrate ? migrateFSRS3Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS3Parameters(weights);
        if (check) checkFSRS3Parameters(weights);
        const $config = fsrs3ConfigSchema.parse({ weights });
        return createFSRS3Model(Object.freeze($config));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-4.mjs
var fsrs_4_exports = {};
__export(fsrs_4_exports, {
  FSRS4Algorithm: () => FSRS4Algorithm,
  FSRS4Model: () => FSRS4Model,
  FSRS4_DEFAULT_WEIGHTS: () => FSRS4_DEFAULT_WEIGHTS,
  FSRS4_MODEL_BOUNDS: () => FSRS4_MODEL_BOUNDS,
  checkFSRS4Parameters: () => checkFSRS4Parameters,
  clipFSRS4Parameters: () => clipFSRS4Parameters,
  forgettingCurve: () => forgetting_curve3,
  fsrs4ConfigSchema: () => fsrs4ConfigSchema,
  migrateFSRS4Parameters: () => migrateFSRS4Parameters
});
function forgetting_curve3(elapsed_days, stability) {
  return roundTo(Math.pow(1 + elapsed_days / (9 * stability), -1), 8);
}
var FSRS4Algorithm, FSRS4_MODEL_BOUNDS, FSRS4_DEFAULT_WEIGHTS, FSRS4ParameterBounds, clipFSRS4Parameters, checkFSRS4Parameters, migrateFSRS4Parameters, fsrs4ConfigSchema, createFSRS4Model, FSRS4Model;
var init_fsrs_4 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-4.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_schema_D7q2J7dh();
    init_error();
    init_esm();
    FSRS4Algorithm = class {
      weights;
      bounds;
      constructor(weights, bounds) {
        this.weights = weights;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 17) throw new FSRSValidationError(`FSRS4Algorithm requires exactly 17 weights, but received ${weights?.length}`);
      }
      init_stability(g) {
        return clamp(this.weights[g - 1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(g) {
        const w = this.weights;
        const d = w[4] - (g - 3) * w[5];
        return clamp(roundTo(d, 8), this.bounds.dMin, this.bounds.dMax);
      }
      next_interval(s, desired_retention) {
        if (!Number.isFinite(desired_retention) || desired_retention <= 0 || desired_retention > 1) throw new FSRSValidationError("Requested retention rate should be in the range (0,1]");
        const intervalModifier = roundTo(9 * (1 / desired_retention - 1), 8);
        return Math.max(Math.round(s * intervalModifier), 1);
      }
      next_difficulty(d, g) {
        const next_d = d - this.weights[6] * (g - 3);
        return clamp(this.mean_reversion(this.weights[4], next_d), this.bounds.dMin, this.bounds.dMax);
      }
      mean_reversion(init, current) {
        const w = this.weights;
        return roundTo(w[7] * init + (1 - w[7]) * current, 8);
      }
      next_recall_stability(d, s, r, g) {
        const w = this.weights;
        const hard_penalty = Rating.Hard === g ? w[15] : 1;
        const easy_bound = Rating.Easy === g ? w[16] : 1;
        return roundTo(clamp(s * (1 + Math.exp(w[8]) * (11 - d) * Math.pow(s, -w[9]) * (Math.exp((1 - r) * w[10]) - 1) * hard_penalty * easy_bound), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_forget_stability(d, s, r) {
        const w = this.weights;
        return roundTo(clamp(w[11] * Math.pow(d, -w[12]) * (Math.pow(s + 1, w[13]) - 1) * Math.exp((1 - r) * w[14]), this.bounds.sMin, this.bounds.sMax), 8);
      }
      forgetting_curve = forgetting_curve3;
      next_state(memory_state, t, g, r) {
        const { difficulty: d, stability: s } = memory_state ?? {
          difficulty: 0,
          stability: 0
        };
        if (t < 0) throw new FSRSValidationError(`Invalid delta_t "${t}"`);
        if (g < 0 || g > 4) throw new FSRSValidationError(`Invalid grade "${g}"`);
        if (g === Rating.Manual) return {
          difficulty: d,
          stability: s
        };
        const grade = g;
        if (d === 0 && s === 0) return {
          difficulty: this.init_difficulty(grade),
          stability: this.init_stability(grade)
        };
        if (d < this.bounds.dMin || s < this.bounds.sMin) throw new FSRSValidationError(`Invalid memory state { difficulty: ${d}, stability: ${s} }`);
        r = typeof r === "number" ? r : this.forgetting_curve(t, s);
        const new_s = grade === Rating.Again ? this.next_forget_stability(d, s, r) : this.next_recall_stability(d, s, r, grade);
        return {
          difficulty: this.next_difficulty(d, grade),
          stability: new_s
        };
      }
    };
    FSRS4_MODEL_BOUNDS = Object.freeze({
      sMin: 0.01,
      sMax: 36500,
      dMin: 1,
      dMax: 10
    });
    FSRS4_DEFAULT_WEIGHTS = Object.freeze([
      0.4,
      0.9,
      2.3,
      10.9,
      4.93,
      0.94,
      0.86,
      0.01,
      1.49,
      0.14,
      0.94,
      2.18,
      0.05,
      0.34,
      1.26,
      0.29,
      2.61
    ]);
    FSRS4ParameterBounds = () => [
      [FSRS4_MODEL_BOUNDS.sMin, FSRS4_MODEL_BOUNDS.sMax],
      [FSRS4_MODEL_BOUNDS.sMin, FSRS4_MODEL_BOUNDS.sMax],
      [FSRS4_MODEL_BOUNDS.sMin, FSRS4_MODEL_BOUNDS.sMax],
      [FSRS4_MODEL_BOUNDS.sMin, FSRS4_MODEL_BOUNDS.sMax],
      [1, 10],
      [0.1, 5],
      [0.1, 5],
      [0, 0.5],
      [0, 3],
      [0.1, 0.8],
      [0.01, 2.5],
      [0.5, 5],
      [0.01, 0.2],
      [0.01, 0.9],
      [0.01, 2],
      [0, 1],
      [1, 4]
    ];
    clipFSRS4Parameters = (parameters) => {
      return FSRS4ParameterBounds().slice(0, parameters.length).map(([min, max], index) => clamp(parameters[index] ?? 0, min, max));
    };
    checkFSRS4Parameters = (parameters) => {
      const clipped = clipFSRS4Parameters(Array.from(parameters));
      if (!(parameters.length === FSRS4_DEFAULT_WEIGHTS.length && clipped.every((value, index) => value === parameters[index]))) throw new FSRSValidationError("Expected FSRS4 weights within model bounds.");
      return parameters;
    };
    migrateFSRS4Parameters = (parameters) => {
      if (!Array.isArray(parameters) || parameters.length === 0) return [...FSRS4_DEFAULT_WEIGHTS];
      return parameters.slice(0, FSRS4_DEFAULT_WEIGHTS.length);
    };
    fsrs4ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights)) return { value: { weights: value.weights } };
      return { issues: [{ message: "Expected FSRS4 config" }] };
    });
    createFSRS4Model = (config) => {
      const bounds = FSRS4_MODEL_BOUNDS;
      const algo = new FSRS4Algorithm(config.weights, FSRS4_MODEL_BOUNDS);
      const step = ({ memoryState, rating, elapsedDays, retrievability }) => {
        return algo.next_state(memoryState, elapsedDays, rating, retrievability);
      };
      const nextInterval = (memoryState, desiredRetention) => {
        return algo.next_interval(memoryState.stability, desiredRetention);
      };
      const forgettingCurve = (memoryState, elapsedDays) => {
        return algo.forgetting_curve(elapsedDays, memoryState.stability);
      };
      const forward = ({ history, initialState }) => {
        const states2 = [];
        let memoryState = initialState || null;
        for (const review of history) {
          memoryState = step({
            memoryState,
            rating: review.rating,
            elapsedDays: review.deltaT
          });
          states2.push(memoryState);
        }
        return states2;
      };
      return {
        config,
        bounds,
        algorithm: algo,
        step,
        nextInterval,
        forgettingCurve,
        forward
      };
    };
    FSRS4Model = defineModel({
      name: "fsrs-4",
      schema: {
        config: fsrs4ConfigSchema,
        memoryState: FSRSMemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS4Model(config);
        let weights = migrate ? migrateFSRS4Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS4Parameters(weights);
        if (check) checkFSRS4Parameters(weights);
        const $config = fsrs4ConfigSchema.parse({ weights });
        return createFSRS4Model(Object.freeze($config));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-4dot5.mjs
var fsrs_4dot5_exports = {};
__export(fsrs_4dot5_exports, {
  FSRS4Dot5Algorithm: () => FSRS4Dot5Algorithm,
  FSRS4Dot5Model: () => FSRS4Dot5Model,
  FSRS4Dot5_DECAY: () => FSRS4Dot5_DECAY,
  FSRS4Dot5_DEFAULT_WEIGHTS: () => FSRS4Dot5_DEFAULT_WEIGHTS,
  FSRS4Dot5_FACTOR: () => FSRS4Dot5_FACTOR,
  FSRS4Dot5_MODEL_BOUNDS: () => FSRS4Dot5_MODEL_BOUNDS,
  checkFSRS4Dot5Parameters: () => checkFSRS4Dot5Parameters,
  clipFSRS4Dot5Parameters: () => clipFSRS4Dot5Parameters,
  forgettingCurve: () => forgetting_curve4,
  fsrs4Dot5ConfigSchema: () => fsrs4Dot5ConfigSchema,
  migrateFSRS4Dot5Parameters: () => migrateFSRS4Dot5Parameters
});
function forgetting_curve4(elapsed_days, stability) {
  return roundTo(Math.pow(1 + FSRS4Dot5_FACTOR * elapsed_days / stability, -FSRS4Dot5_DECAY), 8);
}
var FSRS4Dot5_DECAY, FSRS4Dot5_FACTOR, FSRS4Dot5_MODEL_BOUNDS, FSRS4Dot5_DEFAULT_WEIGHTS, FSRS4Dot5ParameterBounds, FSRS4Dot5Algorithm, clipFSRS4Dot5Parameters, checkFSRS4Dot5Parameters, migrateFSRS4Dot5Parameters, fsrs4Dot5ConfigSchema, createFSRS4Dot5Model, FSRS4Dot5Model;
var init_fsrs_4dot5 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-4dot5.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_schema_D7q2J7dh();
    init_error();
    init_esm();
    FSRS4Dot5_DECAY = 0.5;
    FSRS4Dot5_FACTOR = 19 / 81;
    FSRS4Dot5_MODEL_BOUNDS = Object.freeze({
      sMin: 0.01,
      sMax: 36500,
      dMin: 1,
      dMax: 10
    });
    FSRS4Dot5_DEFAULT_WEIGHTS = Object.freeze([
      0.4872,
      1.4003,
      3.7145,
      13.8206,
      5.1618,
      1.2298,
      0.8975,
      0.031,
      1.6474,
      0.1367,
      1.0461,
      2.1072,
      0.0793,
      0.3246,
      1.587,
      0.2272,
      2.8755
    ]);
    FSRS4Dot5ParameterBounds = () => [
      [FSRS4Dot5_MODEL_BOUNDS.sMin, 100],
      [FSRS4Dot5_MODEL_BOUNDS.sMin, 100],
      [FSRS4Dot5_MODEL_BOUNDS.sMin, 100],
      [FSRS4Dot5_MODEL_BOUNDS.sMin, 100],
      [0, FSRS4Dot5_MODEL_BOUNDS.dMax],
      [0.01, 5],
      [0.01, 5],
      [0, 0.8],
      [0, 6],
      [0, 0.8],
      [0.01, 5],
      [0.2, 6],
      [0.01, 0.4],
      [0.01, 0.9],
      [0.01, 4],
      [0, 1],
      [1, 10]
    ];
    FSRS4Dot5Algorithm = class {
      weights;
      bounds;
      constructor(weights, bounds) {
        this.weights = weights;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 17) throw new FSRSValidationError(`FSRS4Dot5Algorithm requires exactly 17 weights, but received ${weights?.length}`);
      }
      init_stability(g) {
        return clamp(this.weights[g - 1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(g) {
        const w = this.weights;
        const d = w[4] - (g - 3) * w[5];
        return clamp(roundTo(d, 8), this.bounds.dMin, this.bounds.dMax);
      }
      next_interval(s, desired_retention) {
        if (!Number.isFinite(desired_retention) || desired_retention <= 0 || desired_retention > 1) throw new FSRSValidationError("Desired retention rate should be in the range (0,1]");
        const intervalModifier = roundTo((Math.pow(desired_retention, 1 / -FSRS4Dot5_DECAY) - 1) / FSRS4Dot5_FACTOR, 8);
        return Math.max(Math.round(s * intervalModifier), 1);
      }
      next_difficulty(d, g) {
        const next_d = d - this.weights[6] * (g - 3);
        return clamp(this.mean_reversion(this.weights[4], next_d), this.bounds.dMin, this.bounds.dMax);
      }
      mean_reversion(init, current) {
        const w = this.weights;
        return roundTo(w[7] * init + (1 - w[7]) * current, 8);
      }
      next_recall_stability(d, s, r, g) {
        const w = this.weights;
        const hard_penalty = Rating.Hard === g ? w[15] : 1;
        const easy_bound = Rating.Easy === g ? w[16] : 1;
        return roundTo(clamp(s * (1 + Math.exp(w[8]) * (11 - d) * Math.pow(s, -w[9]) * (Math.exp((1 - r) * w[10]) - 1) * hard_penalty * easy_bound), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_forget_stability(d, s, r) {
        const w = this.weights;
        const next_s = w[11] * Math.pow(d, -w[12]) * (Math.pow(s + 1, w[13]) - 1) * Math.exp((1 - r) * w[14]);
        return roundTo(clamp(Math.min(next_s, s), this.bounds.sMin, this.bounds.sMax), 8);
      }
      forgetting_curve = forgetting_curve4;
      next_state(memory_state, t, g, r) {
        const { difficulty: d, stability: s } = memory_state ?? {
          difficulty: 0,
          stability: 0
        };
        if (t < 0) throw new FSRSValidationError(`Invalid delta_t "${t}"`);
        if (g < 0 || g > 4) throw new FSRSValidationError(`Invalid grade "${g}"`);
        if (g === Rating.Manual) return {
          difficulty: d,
          stability: s
        };
        const grade = g;
        if (d === 0 && s === 0) return {
          difficulty: this.init_difficulty(grade),
          stability: this.init_stability(grade)
        };
        if (d < this.bounds.dMin || s < this.bounds.sMin) throw new FSRSValidationError(`Invalid memory state { difficulty: ${d}, stability: ${s} }`);
        r = typeof r === "number" ? r : this.forgetting_curve(t, s);
        const new_s = g === Rating.Again ? this.next_forget_stability(d, s, r) : this.next_recall_stability(d, s, r, grade);
        return {
          difficulty: this.next_difficulty(d, grade),
          stability: new_s
        };
      }
    };
    clipFSRS4Dot5Parameters = (parameters) => {
      return FSRS4Dot5ParameterBounds().slice(0, parameters.length).map(([min, max], index) => clamp(parameters[index] || 0, min, max));
    };
    checkFSRS4Dot5Parameters = (parameters) => {
      const clipped = clipFSRS4Dot5Parameters(Array.from(parameters));
      if (!(parameters.length === FSRS4Dot5_DEFAULT_WEIGHTS.length && clipped.every((value, index) => value === parameters[index]))) throw new FSRSValidationError("Expected FSRS4.5 weights within model bounds.");
      return parameters;
    };
    migrateFSRS4Dot5Parameters = (parameters) => {
      if (!Array.isArray(parameters) || parameters.length === 0) return [...FSRS4Dot5_DEFAULT_WEIGHTS];
      return parameters.slice(0, FSRS4Dot5_DEFAULT_WEIGHTS.length);
    };
    fsrs4Dot5ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights)) return { value: { weights: value.weights } };
      return { issues: [{ message: "Expected FSRS4.5 config" }] };
    });
    createFSRS4Dot5Model = (config) => {
      const bounds = FSRS4Dot5_MODEL_BOUNDS;
      const algo = new FSRS4Dot5Algorithm(config.weights, FSRS4Dot5_MODEL_BOUNDS);
      const step = ({ memoryState, rating, elapsedDays, retrievability }) => {
        return algo.next_state(memoryState, elapsedDays, rating, retrievability);
      };
      const nextInterval = (memoryState, desiredRetention) => {
        return algo.next_interval(memoryState.stability, desiredRetention);
      };
      const forgettingCurve = (memoryState, elapsedDays) => {
        return algo.forgetting_curve(elapsedDays, memoryState.stability);
      };
      const forward = ({ history, initialState }) => {
        const states2 = [];
        let memoryState = initialState || null;
        for (const review of history) {
          memoryState = step({
            memoryState,
            rating: review.rating,
            elapsedDays: review.deltaT
          });
          states2.push(memoryState);
        }
        return states2;
      };
      return {
        config,
        bounds,
        algorithm: algo,
        step,
        nextInterval,
        forgettingCurve,
        forward
      };
    };
    FSRS4Dot5Model = defineModel({
      name: "fsrs-4dot5",
      schema: {
        config: fsrs4Dot5ConfigSchema,
        memoryState: FSRSMemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS4Dot5Model(config);
        let weights = migrate ? migrateFSRS4Dot5Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS4Dot5Parameters(weights);
        if (check) checkFSRS4Dot5Parameters(weights);
        const $config = fsrs4Dot5ConfigSchema.parse({ weights });
        return createFSRS4Dot5Model(Object.freeze($config));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-5.mjs
var fsrs_5_exports = {};
__export(fsrs_5_exports, {
  FSRS5Algorithm: () => FSRS5Algorithm,
  FSRS5Model: () => FSRS5Model,
  FSRS5_DECAY: () => FSRS5_DECAY,
  FSRS5_DEFAULT_WEIGHTS: () => FSRS5_DEFAULT_WEIGHTS,
  FSRS5_FACTOR: () => FSRS5_FACTOR,
  FSRS5_MODEL_BOUNDS: () => FSRS5_MODEL_BOUNDS,
  FSRS5_W17_W18_CEILING: () => FSRS5_W17_W18_CEILING,
  checkFSRS5Parameters: () => checkFSRS5Parameters,
  clipFSRS5Parameters: () => clipFSRS5Parameters,
  forgettingCurve: () => forgetting_curve5,
  fsrs5ConfigSchema: () => fsrs5ConfigSchema,
  migrateFSRS5Parameters: () => migrateFSRS5Parameters
});
function forgetting_curve5(elapsed_days, stability) {
  return roundTo(Math.pow(1 + FSRS5_FACTOR * elapsed_days / stability, -FSRS5_DECAY), 8);
}
var FSRS5Algorithm, clipFSRS5Parameters, checkFSRS5Parameters, migrateFSRS5Parameters, fsrs5ConfigSchema, createFSRS5Model, FSRS5Model;
var init_fsrs_5 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-5.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_schema_D7q2J7dh();
    init_error();
    init_constants_YU7EeO_L();
    init_esm();
    FSRS5Algorithm = class {
      weights;
      enableShortTerm;
      bounds;
      constructor(weights, enableShortTerm, bounds) {
        this.weights = weights;
        this.enableShortTerm = enableShortTerm;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 19) throw new FSRSValidationError(`FSRS5Algorithm requires exactly 19 weights, but received ${weights?.length}`);
      }
      init_stability(g) {
        return clamp(this.weights[g - 1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(g) {
        const w = this.weights;
        const d = w[4] - Math.exp((g - 1) * w[5]) + 1;
        return clamp(roundTo(d, 8), this.bounds.dMin, this.bounds.dMax);
      }
      next_interval(s, desired_retention) {
        if (!Number.isFinite(desired_retention) || desired_retention <= 0 || desired_retention > 1) throw new FSRSValidationError("Requested retention rate should be in the range (0,1]");
        const intervalModifier = roundTo((Math.pow(desired_retention, 1 / -FSRS5_DECAY) - 1) / FSRS5_FACTOR, 8);
        return Math.max(Math.round(s * intervalModifier), 1);
      }
      /**
      * @see https://github.com/open-spaced-repetition/fsrs4anki/issues/697
      */
      linear_damping(delta_d, old_d) {
        return roundTo(delta_d * (10 - old_d) / 9, 8);
      }
      next_difficulty(d, g) {
        const delta_d = -this.weights[6] * (g - 3);
        const next_d = d + this.linear_damping(delta_d, d);
        return clamp(this.mean_reversion(this.init_difficulty(Rating.Easy), next_d), this.bounds.dMin, this.bounds.dMax);
      }
      mean_reversion(init, current) {
        const w = this.weights;
        return roundTo(w[7] * init + (1 - w[7]) * current, 8);
      }
      next_recall_stability(d, s, r, g) {
        const w = this.weights;
        const hard_penalty = Rating.Hard === g ? w[15] : 1;
        const easy_bound = Rating.Easy === g ? w[16] : 1;
        return roundTo(clamp(s * (1 + Math.exp(w[8]) * (11 - d) * Math.pow(s, -w[9]) * (Math.exp((1 - r) * w[10]) - 1) * hard_penalty * easy_bound), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_forget_stability(d, s, r) {
        const w = this.weights;
        return roundTo(clamp(w[11] * Math.pow(d, -w[12]) * (Math.pow(s + 1, w[13]) - 1) * Math.exp((1 - r) * w[14]), this.bounds.sMin, this.bounds.sMax), 8);
      }
      next_short_term_stability(s, g) {
        const w = this.weights;
        return roundTo(clamp(s * Math.exp(w[17] * (g - 3 + w[18])), this.bounds.sMin, this.bounds.sMax), 8);
      }
      forgetting_curve = forgetting_curve5;
      next_state(memory_state, t, g, r) {
        const { difficulty: d, stability: s } = memory_state ?? {
          difficulty: 0,
          stability: 0
        };
        if (t < 0) throw new FSRSValidationError(`Invalid delta_t "${t}"`);
        if (g < 0 || g > 4) throw new FSRSValidationError(`Invalid grade "${g}"`);
        if (g === Rating.Manual) return {
          difficulty: d,
          stability: s
        };
        const grade = g;
        if (d === 0 && s === 0) return {
          difficulty: this.init_difficulty(grade),
          stability: this.init_stability(grade)
        };
        if (d < this.bounds.dMin || s < this.bounds.sMin) throw new FSRSValidationError(`Invalid memory state { difficulty: ${d}, stability: ${s} }`);
        r = typeof r === "number" ? r : this.forgetting_curve(t, s);
        let new_s;
        if (t === 0 && this.enableShortTerm) new_s = this.next_short_term_stability(s, grade);
        else if (g === Rating.Again) {
          const s_after_fail = this.next_forget_stability(d, s, r);
          let [w_17, w_18] = [0, 0];
          if (this.enableShortTerm) {
            w_17 = this.weights[17];
            w_18 = this.weights[18];
          }
          const next_s_min = s / Math.exp(w_17 * w_18);
          new_s = clamp(roundTo(next_s_min, 8), this.bounds.sMin, s_after_fail);
        } else new_s = this.next_recall_stability(d, s, r, grade);
        return {
          difficulty: this.next_difficulty(d, grade),
          stability: new_s
        };
      }
    };
    clipFSRS5Parameters = (parameters) => {
      return FSRS5ParameterBounds().slice(0, parameters.length).map(([min, max], index) => clamp(parameters[index] || 0, min, max));
    };
    checkFSRS5Parameters = (parameters) => {
      const clipped = clipFSRS5Parameters(Array.from(parameters));
      if (!(parameters.length === FSRS5_DEFAULT_WEIGHTS.length && clipped.every((value, index) => value === parameters[index]))) throw new FSRSValidationError("Expected FSRS5 weights within model bounds.");
      return parameters;
    };
    migrateFSRS5Parameters = (parameters) => {
      if (!Array.isArray(parameters) || parameters.length === 0) return [...FSRS5_DEFAULT_WEIGHTS];
      if (parameters.length > 19) return parameters.slice(0, 19);
      switch (parameters.length) {
        case 19:
          return Array.from(parameters);
        case 17: {
          const weights = Array.from(parameters);
          weights[4] = roundTo(weights[5] * 2 + weights[4], 8);
          weights[5] = roundTo(Math.log(weights[5] * 3 + 1) / 3, 8);
          weights[6] = roundTo(weights[6] + 0.5, 8);
          return weights.concat([0, 0]);
        }
        default:
          throw new FSRSValidationError(`Invalid parameters length "${parameters.length}", expected 17 or 19.`);
      }
    };
    fsrs5ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights) && typeof value.enableShortTerm === "boolean") return { value: {
        weights: value.weights,
        enableShortTerm: value.enableShortTerm
      } };
      return { issues: [{ message: "Expected FSRS5 config" }] };
    });
    createFSRS5Model = (config) => {
      const bounds = FSRS5_MODEL_BOUNDS;
      const algo = new FSRS5Algorithm(config.weights, config.enableShortTerm, FSRS5_MODEL_BOUNDS);
      const step = ({ memoryState, rating, elapsedDays, retrievability }) => {
        return algo.next_state(memoryState, elapsedDays, rating, retrievability);
      };
      const nextInterval = (memoryState, desiredRetention) => {
        return algo.next_interval(memoryState.stability, desiredRetention);
      };
      const forgettingCurve = (memoryState, elapsedDays) => {
        return algo.forgetting_curve(elapsedDays, memoryState.stability);
      };
      const forward = ({ history, initialState }) => {
        const states2 = [];
        let memoryState = initialState || null;
        for (const review of history) {
          memoryState = step({
            memoryState,
            rating: review.rating,
            elapsedDays: review.deltaT
          });
          states2.push(memoryState);
        }
        return states2;
      };
      return {
        config,
        bounds,
        algorithm: algo,
        step,
        nextInterval,
        forgettingCurve,
        forward
      };
    };
    FSRS5Model = defineModel({
      name: "fsrs-5",
      schema: {
        config: fsrs5ConfigSchema,
        memoryState: FSRSMemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS5Model(config);
        let weights = migrate ? migrateFSRS5Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS5Parameters(weights);
        if (check) checkFSRS5Parameters(weights);
        const $config = fsrs5ConfigSchema.parse({
          weights,
          enableShortTerm: config.enableShortTerm
        });
        return createFSRS5Model(Object.freeze($config));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-6.mjs
var fsrs_6_exports = {};
__export(fsrs_6_exports, {
  FSRS6Algorithm: () => FSRS6Algorithm,
  FSRS6Model: () => FSRS6Model,
  FSRS6_DECAY: () => FSRS6_DECAY,
  FSRS6_DEFAULT_WEIGHTS: () => FSRS6_DEFAULT_WEIGHTS,
  FSRS6_MODEL_BOUNDS: () => FSRS6_MODEL_BOUNDS,
  FSRS6_W17_W18_CEILING: () => FSRS6_W17_W18_CEILING,
  checkFSRS6Parameters: () => checkFSRS6Parameters,
  clipFSRS6Parameters: () => clipFSRS6Parameters,
  computeDecayFactor: () => computeDecayFactor,
  decaySchema: () => decaySchema,
  forgettingCurve: () => forgetting_curve,
  fsrs6ConfigSchema: () => fsrs6ConfigSchema,
  migrateFSRS6Parameters: () => migrateFSRS6Parameters
});
var init_fsrs_6 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-6.mjs"() {
    init_fsrs_6_Bt0f3F6X();
  }
});

// node_modules/ts-fsrs/dist/models/fsrs-7.mjs
var fsrs_7_exports = {};
__export(fsrs_7_exports, {
  FSRS7Algorithm: () => FSRS7Algorithm,
  FSRS7MemoryStateSchema: () => FSRS7MemoryStateSchema,
  FSRS7Model: () => FSRS7Model,
  FSRS7ParameterBounds: () => FSRS7ParameterBounds,
  FSRS7_DEFAULT_WEIGHTS: () => FSRS7_DEFAULT_WEIGHTS,
  FSRS7_MODEL_BOUNDS: () => FSRS7_MODEL_BOUNDS,
  checkFSRS7Parameters: () => checkFSRS7Parameters,
  clipFSRS7Parameters: () => clipFSRS7Parameters,
  curve: () => curve,
  decaySchema: () => decaySchema2,
  fsrs7ConfigSchema: () => fsrs7ConfigSchema,
  migrateFSRS7Parameters: () => migrateFSRS7Parameters
});
function prepare_fast(w, s) {
  const decay = -clamp(w[23] * Math.pow(s, w[33] - 0.3), 0.01, 0.95);
  return {
    decay,
    scale: (Math.exp(Math.min(Math.log(w[25]) / decay, 60)) - 1) / s
  };
}
function fast_component(t, params) {
  const days = Math.max(t, 0);
  const { decay, scale } = params;
  const base = 1 + scale * days;
  return {
    recall: Math.pow(base, decay),
    derivative: decay * Math.pow(base, decay - 1) * scale
  };
}
function prepare_curve(w, state, bounds) {
  const { sMin: sMin2, sMax, stabilityFastMin, stabilityFastMax, dMin: dMin2, dMax: dMax2 } = bounds;
  const s = clamp(state.stability, sMin2, sMax);
  const sFast = clamp(state.stabilityFast, stabilityFastMin, stabilityFastMax);
  const d = clamp(state.difficulty, dMin2, dMax2);
  const fast = prepare_fast(w, sFast);
  const decay = -clamp(w[24], 0.01, 0.95);
  const scale = (Math.pow(w[26], 1 / decay) - 1) * Math.exp((d - 5) * (w[32] - 0.3)) / s;
  const weight1 = w[27] * Math.pow(sFast, -w[29]);
  const weight2 = w[28] * Math.pow(s, w[30]) * Math.exp((d - 5) * (w[31] - 0.5));
  return {
    fast,
    decay,
    scale,
    weight1,
    weight2,
    total: weight1 + weight2
  };
}
function compute_curve(t, params) {
  const { decay, scale, weight1, weight2, total } = params;
  const days = Math.max(t, 0);
  const fast = fast_component(days, params.fast);
  const base = 1 + scale * days;
  const slow = Math.pow(base, decay);
  const derivative = decay * Math.pow(base, decay - 1) * scale;
  return {
    retrievability: (weight1 * fast.recall + weight2 * slow) / total * 0.99998 + 1e-5,
    derivative: (weight1 * fast.derivative + weight2 * derivative) / total * 0.99998,
    fast: fast.recall,
    slow,
    fastWeight: weight1,
    slowWeight: weight2,
    total
  };
}
function curve(weights, elapsedDays, state) {
  return compute_curve(elapsedDays, prepare_curve(weights, state, FSRS7_MODEL_BOUNDS));
}
function clipFSRS7Parameters(parameters) {
  const clipped = Array.from(parameters);
  if (clipped.length < FSRS7_DEFAULT_WEIGHTS.length) return clipped;
  for (const [index, [min, max]] of FSRS7ParameterBounds().entries()) {
    const low = index > 0 && index < 4 ? Math.max(min, clipped[index - 1]) : index === 26 ? Math.max(min, clipped[25]) : min;
    clipped[index] = clamp(Number.isFinite(clipped[index]) ? clipped[index] : low, low, max);
  }
  return clipped;
}
function checkFSRS7Parameters(parameters) {
  if (parameters.length !== FSRS7_DEFAULT_WEIGHTS.length || !clipFSRS7Parameters(parameters).every((value, index) => value === parameters[index])) throw new FSRSValidationError("Expected FSRS7 weights within model bounds.");
  return parameters;
}
function migrateFSRS7Parameters(parameters) {
  if (!parameters || parameters.length === 0) return [...FSRS7_DEFAULT_WEIGHTS];
  if (parameters.length !== FSRS7_DEFAULT_WEIGHTS.length) throw new FSRSValidationError(`Invalid parameters length "${parameters.length}", expected 34. FSRS-7 requires its own weights; replay review history to migrate memory states.`);
  return Array.from(parameters);
}
function createFSRS7Model(config) {
  const bounds = FSRS7_MODEL_BOUNDS;
  const algorithm = new FSRS7Algorithm(config.weights, bounds);
  return {
    config,
    bounds,
    algorithm,
    step: ({ memoryState, elapsedDays, rating, retrievability }) => algorithm.next_state(memoryState, elapsedDays, rating, retrievability),
    nextInterval: (state, desiredRetention) => algorithm.next_interval(state, desiredRetention),
    forgettingCurve: (state, elapsedDays) => algorithm.curve(elapsedDays, state).retrievability,
    forward({ history, initialState }) {
      const states2 = [];
      let state = initialState ?? null;
      for (const { rating, deltaT } of history) {
        state = algorithm.next_state(state, deltaT, rating);
        states2.push(state);
      }
      return states2;
    }
  };
}
var FSRS7_MODEL_BOUNDS, sMin, dMin, dMax, FSRS7ParameterBounds, FSRS7_DEFAULT_WEIGHTS, MIN_T, LOG_MIN_T, DR_MIN, DR_MAX, FSRS7Algorithm, decaySchema2, fsrs7ConfigSchema, FSRS7MemoryStateSchema, FSRS7Model;
var init_fsrs_7 = __esm({
  "node_modules/ts-fsrs/dist/models/fsrs-7.mjs"() {
    init_schema_utils_DX7uVwiJ();
    init_error();
    init_esm();
    FSRS7_MODEL_BOUNDS = Object.freeze({
      sMin: 1e-4,
      sMax: 36500,
      stabilityFastMin: 1e-4,
      stabilityFastMax: 36500,
      dMin: 1,
      dMax: 10
    });
    ({ sMin, dMin, dMax } = FSRS7_MODEL_BOUNDS);
    FSRS7ParameterBounds = () => [
      [sMin, 100 / 2],
      [sMin, 100],
      [sMin, 100],
      [sMin, 100],
      [dMin, dMax],
      [1e-3, 4],
      [0.1, 4],
      [0, 4],
      [0, 1.2],
      [0.3, 3],
      [0.01, 1.5],
      [0.1, 1],
      [0, 3.5],
      [0, 1],
      [1, 7],
      [0, 4],
      [0, 2],
      [0.5, 6],
      [1e-3, 1.5],
      [1e-3, 1],
      [0, 5],
      [0, 1],
      [1, 7],
      [0.01, 0.25],
      [0.01, 0.95],
      [0.2, 0.85],
      [0.5, 0.99],
      [0.01, 1],
      [0.1, 1],
      [0, 0.9],
      [0.1, 1.1],
      [0, 1],
      [0, 0.6],
      [0, 0.6]
    ];
    FSRS7_DEFAULT_WEIGHTS = Object.freeze([
      0.1104,
      2.2395,
      3.9221,
      11.7841,
      6.1686,
      0.6457,
      3.6807,
      1.9795,
      0,
      1.3826,
      0.7024,
      0.5999,
      0.8146,
      0.6398,
      1,
      1.3207,
      0.6707,
      3.8668,
      0.4416,
      0.0934,
      1.8631,
      0.6162,
      1.0869,
      0.1567,
      0.0801,
      0.2421,
      0.9464,
      0.1433,
      0.7145,
      0,
      0.5667,
      0.3734,
      0.5333,
      0.3048
    ]);
    MIN_T = 1 / 86400;
    LOG_MIN_T = Math.log(MIN_T);
    DR_MIN = 1e-4;
    DR_MAX = 0.9999;
    FSRS7Algorithm = class {
      weights;
      bounds;
      logSMax;
      constructor(weights, bounds) {
        this.weights = weights;
        this.bounds = bounds;
        if (!Array.isArray(weights) || weights.length !== 34 || !weights.every(Number.isFinite)) throw new FSRSValidationError("FSRS7Algorithm requires exactly 34 finite weights");
        this.logSMax = Math.log(bounds.sMax);
      }
      init_stability(grade) {
        return clamp(this.weights[grade - 1], this.bounds.sMin, this.bounds.sMax);
      }
      init_difficulty(grade) {
        const w = this.weights;
        return w[4] - Math.exp(w[5] * (grade - 1)) + 1;
      }
      /**
      * Retrievability and its elapsed-day derivative, plus the raw trace recalls
      * and the unnormalised weights mixing them.
      */
      curve(t, state) {
        return compute_curve(t, prepare_curve(this.weights, state, this.bounds));
      }
      /** Raw fractional days for retention in (0,1); rates >= 0.9999 yield zero. */
      next_interval(state, desiredRetention) {
        const { sMin: sMin2, sMax, stabilityFastMin, stabilityFastMax } = this.bounds;
        if (!Number.isFinite(desiredRetention) || desiredRetention <= 0 || desiredRetention >= 1) throw new FSRSValidationError("Desired retention rate should be in the range (0,1)");
        const target = clamp(desiredRetention, DR_MIN, DR_MAX);
        if (target >= 0.9999) return 0;
        const s = clamp(state.stability, sMin2, sMax);
        const sFast = clamp(state.stabilityFast, stabilityFastMin, stabilityFastMax);
        const maxStability = Math.max(s, sFast);
        const params = prepare_curve(this.weights, state, this.bounds);
        let logT = Math.log(maxStability);
        for (let i = 0; i < 7; i++) {
          logT = clamp(logT, LOG_MIN_T, this.logSMax);
          const t = clamp(Math.exp(logT), MIN_T, sMax);
          const { retrievability, derivative } = compute_curve(t, params);
          logT -= clamp((retrievability - target) / Math.min(derivative * t, -1e-12), -4, 4);
          if (!Number.isFinite(logT)) break;
        }
        const interval = clamp(Math.exp(logT), 0, sMax);
        if (Math.abs(compute_curve(interval, params).retrievability - target) <= 1e-3) return interval;
        let low = 0;
        let high = Math.min(Math.max(maxStability, 1), sMax);
        while (compute_curve(high, params).retrievability > target && high < sMax) high = Math.min(high * 2, sMax);
        for (let i = 0; i < 50; i++) {
          const mid = (low + high) / 2;
          if (compute_curve(mid, params).retrievability > target) low = mid;
          else high = mid;
        }
        return (low + high) / 2;
      }
      next_stability(s, d, r, grade, start) {
        const w = this.weights;
        const fail = w[start + 3] * (Math.pow(s + 1, w[start + 4]) - 1) * Math.exp((1 - r) * w[start + 5]);
        const pls = Math.min(s, fail);
        if (grade === Rating.Again) return pls;
        const hardPenalty = grade === Rating.Hard ? w[start + 6] : 1;
        const easyBonus = grade === Rating.Easy ? w[start + 7] : 1;
        const increase = Math.exp(w[start] - 1.5) * (11 - d) * Math.pow(s, -w[start + 1]) * (Math.exp((1 - r) * w[start + 2]) - 1) * hardPenalty * easyBonus + 1;
        return Math.max(pls, s * increase);
      }
      next_state(memoryState, elapsedDays, rating, retrievability) {
        const { sMin: sMin2, sMax, stabilityFastMin, stabilityFastMax, dMin: dMin2, dMax: dMax2 } = this.bounds;
        if (!Number.isSafeInteger(rating) || rating < Rating.Manual || rating > Rating.Easy) throw new FSRSValidationError(`Invalid grade "${rating}"`);
        const state = memoryState === null ? {
          stability: 0,
          stabilityFast: 0,
          difficulty: 0
        } : memoryState;
        if (rating === Rating.Manual) return {
          stability: state.stability,
          stabilityFast: state.stabilityFast,
          difficulty: state.difficulty
        };
        const grade = rating;
        if (state.stability === 0 && state.stabilityFast === 0 && state.difficulty === 0) {
          const stability2 = this.init_stability(grade);
          return {
            stability: clamp(roundTo(stability2, 8), sMin2, sMax),
            stabilityFast: clamp(roundTo(stability2 * 0.8, 8), stabilityFastMin, stabilityFastMax),
            difficulty: clamp(roundTo(this.init_difficulty(grade), 8), dMin2, dMax2)
          };
        }
        if (state.stability <= 0 || state.stabilityFast <= 0) throw new FSRSValidationError("Invalid FSRS7 memory state: both stabilities must be positive");
        if (retrievability !== void 0 && (!Number.isFinite(retrievability) || retrievability <= 0 || retrievability >= 1)) throw new FSRSValidationError("Retrievability should be in the range (0,1)");
        const s = clamp(state.stability, sMin2, sMax);
        const sFast = clamp(state.stabilityFast, stabilityFastMin, stabilityFastMax);
        const d = clamp(state.difficulty, dMin2, dMax2);
        const r = retrievability ?? compute_curve(elapsedDays, prepare_curve(this.weights, state, this.bounds)).retrievability;
        const stability = this.next_stability(s, d, r, grade, 7);
        let stabilityFast = this.next_stability(sFast, d, fast_component(elapsedDays, prepare_fast(this.weights, sFast)).recall, grade, 15);
        if (grade === Rating.Again) stabilityFast = Math.min(stabilityFast, stability * 0.8);
        let deltaD = -this.weights[6] * (grade - 3);
        if (grade === Rating.Again) deltaD *= r + 0.1;
        const difficulty = 0.01 * this.init_difficulty(Rating.Easy) + 0.99 * (d + (10 - d) * deltaD / 9);
        return {
          stability: clamp(roundTo(stability, 8), sMin2, sMax),
          stabilityFast: clamp(roundTo(stabilityFast, 8), stabilityFastMin, stabilityFastMax),
          difficulty: clamp(roundTo(difficulty, 8), dMin2, dMax2)
        };
      }
    };
    decaySchema2 = defineSchema((value) => {
      if (isFiniteNumber(value) && value >= 0.01 && value <= 0.95) return { value };
      return { issues: [{ message: "Expected finite decay in the range [0.01, 0.95]" }] };
    });
    fsrs7ConfigSchema = defineSchema((value) => {
      if (isObject2(value) && isNumberArray(value.weights) && value.weights.length === FSRS7_DEFAULT_WEIGHTS.length) return { value: { weights: value.weights } };
      return { issues: [{ message: `Expected FSRS7 config with exactly ${FSRS7_DEFAULT_WEIGHTS.length} finite weights` }] };
    });
    FSRS7MemoryStateSchema = defineSchema((value) => {
      if (isObject2(value) && isFiniteNumber(value.stability) && isFiniteNumber(value.stabilityFast) && isFiniteNumber(value.difficulty)) return { value: {
        stability: value.stability,
        stabilityFast: value.stabilityFast,
        difficulty: value.difficulty
      } };
      return { issues: [{ message: "Expected FSRS7 memory state with finite stability, stabilityFast and difficulty" }] };
    });
    FSRS7Model = defineModel({
      name: "fsrs-7",
      schema: {
        config: fsrs7ConfigSchema,
        memoryState: FSRS7MemoryStateSchema
      },
      defaultValue: { memoryState() {
        return {
          stability: 0,
          stabilityFast: 0,
          difficulty: 0
        };
      } },
      create({ config, migrate = true, clip = true, check = true, bypass = false }) {
        if (bypass) return createFSRS7Model(config);
        let weights = migrate ? migrateFSRS7Parameters(config.weights) : config.weights;
        if (clip && Array.isArray(weights)) weights = clipFSRS7Parameters(weights);
        if (check) checkFSRS7Parameters(weights);
        return createFSRS7Model(Object.freeze(fsrs7ConfigSchema.parse({ weights })));
      }
    });
  }
});

// node_modules/ts-fsrs/dist/index.mjs
init_schema_utils_DX7uVwiJ();
init_schema_D7q2J7dh();
init_error();

// node_modules/ts-fsrs/dist/middlewares-DSIyRr_E.mjs
init_schema_utils_DX7uVwiJ();
init_schema_D7q2J7dh();
init_error();
init_esm();

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/middleware/index.js
init_middleware_CkL5v5zL();

// node_modules/ts-fsrs/dist/middlewares-DSIyRr_E.mjs
var FUZZ_RANGES = Object.freeze([
  {
    start: 2.5,
    end: 7,
    factor: 0.15
  },
  {
    start: 7,
    end: 20,
    factor: 0.1
  },
  {
    start: 20,
    end: Number.POSITIVE_INFINITY,
    factor: 0.05
  }
]);
function getFuzzRange(interval, elapsedDays, maximumInterval, fuzzRanges = FUZZ_RANGES) {
  let delta = 1;
  for (const range of fuzzRanges) delta += range.factor * Math.max(Math.min(interval, range.end) - range.start, 0);
  const cappedInterval = Math.min(interval, maximumInterval);
  let minInterval = Math.max(2, Math.round(cappedInterval - delta));
  const maxInterval = Math.min(Math.round(cappedInterval + delta), maximumInterval);
  if (cappedInterval > elapsedDays) minInterval = Math.max(minInterval, elapsedDays + 1);
  minInterval = Math.min(minInterval, maxInterval);
  return {
    minInterval,
    maxInterval
  };
}
function fnv1a32(str) {
  let hash = 2166136261;
  for (let index = 0; index < str.length; index += 1) {
    hash ^= str.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    let t = a += 1831565813;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
var fnv1aMulberry32Rng = (seed) => mulberry32(fnv1a32(seed));
function withFuzzing(interval, elapsedDays, config, seed) {
  if (!config.enableFuzz || interval < 2.5) return config.fractionalDays ? interval : Math.round(interval);
  const { minInterval, maxInterval } = getFuzzRange(interval, elapsedDays, config.maximumInterval);
  const fuzzFactor = fnv1aMulberry32Rng(seed ?? String(Date.now()))();
  return Math.floor(fuzzFactor * (maxInterval - minInterval + 1) + minInterval);
}
var DECIMAL_PATTERN = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
var ConvertStepUnitToMinutes = (step) => {
  if (typeof step !== "string" || step.length < 2) throw new FSRSValidationError(`Invalid step value: ${step}`);
  const unit = step.slice(-1);
  const numericPart = step.slice(0, -1);
  if (!DECIMAL_PATTERN.test(numericPart)) throw new FSRSValidationError(`Invalid step value: ${step}`);
  const value = Number(numericPart);
  if (!Number.isFinite(value)) throw new FSRSValidationError(`Invalid step value: ${step}`);
  let minutes;
  switch (unit) {
    case "m":
      minutes = value;
      break;
    case "h":
      minutes = value * 60;
      break;
    case "d":
      minutes = value * 1440;
      break;
    default:
      throw new FSRSValidationError(`Invalid step unit: ${step}, expected m/h/d`);
  }
  if (!Number.isFinite(minutes) || !Number.isFinite(minutes * 60)) throw new FSRSValidationError(`Invalid step value: ${step}`);
  return minutes;
};
var calculateLearningSteps = (config, state, learningStep) => {
  const steps = state === State.Relearning || state === State.Review ? config.relearningSteps : config.learningSteps;
  const stepsLength = steps.length;
  if (stepsLength === 0 || learningStep >= stepsLength) return {};
  const learningStepUnit = steps[Math.max(0, learningStep)];
  if (state === State.Review) return { [Rating.Again]: {
    scheduledMinutes: ConvertStepUnitToMinutes(learningStepUnit),
    nextStep: 0
  } };
  const firstMinutes = ConvertStepUnitToMinutes(steps[0]);
  const secondMinutes = stepsLength > 1 ? ConvertStepUnitToMinutes(steps[1]) : void 0;
  const hardMinutes = secondMinutes === void 0 ? firstMinutes * 1.5 : (firstMinutes + secondMinutes) / 2;
  const result = {
    [Rating.Again]: {
      scheduledMinutes: firstMinutes,
      nextStep: 0
    },
    [Rating.Hard]: {
      scheduledMinutes: hardMinutes,
      nextStep: learningStep
    }
  };
  const nextStepUnit = steps[learningStep + 1];
  if (nextStepUnit) {
    const nextMinutes = learningStep === 0 && secondMinutes !== void 0 ? secondMinutes : ConvertStepUnitToMinutes(nextStepUnit);
    if (nextMinutes > 0) result[Rating.Good] = {
      scheduledMinutes: nextMinutes,
      nextStep: learningStep + 1
    };
  }
  return result;
};
var defaultLearningSteps = Object.freeze(["1m", "10m"]);
var defaultRelearningSteps = Object.freeze(["10m"]);
var defaultGraduatingInterval = 1;
function isStepUnit(value) {
  if (typeof value !== "string") return false;
  try {
    const minutes = ConvertStepUnitToMinutes(value);
    return Number.isFinite(minutes * 9e4);
  } catch {
    return false;
  }
}
function isStepList(value) {
  if (!Array.isArray(value) || Object.getOwnPropertyNames(value).length - 1 < value.length) return false;
  for (let index = 0; index < value.length; index++) if (!Object.hasOwn(value, index) || !isStepUnit(value[index])) return false;
  return true;
}
var learningStepsConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected learning steps config object" }] };
  const { enableShortTerm, learningSteps, relearningSteps } = value;
  if (typeof enableShortTerm !== "boolean") return { issues: [{ message: "Expected enableShortTerm boolean" }] };
  if (!isStepList(learningSteps)) return { issues: [{ message: "Expected valid learningSteps array" }] };
  if (!isStepList(relearningSteps)) return { issues: [{ message: "Expected valid relearningSteps array" }] };
  const { graduatingInterval = 1, allowModelOverride = false } = value;
  if (!isFiniteNumber(graduatingInterval) || graduatingInterval <= 0) return { issues: [{ message: "Expected positive graduatingInterval days" }] };
  if (typeof allowModelOverride !== "boolean") return { issues: [{ message: "Expected allowModelOverride boolean" }] };
  return { value: {
    enableShortTerm,
    learningSteps,
    relearningSteps,
    graduatingInterval,
    allowModelOverride
  } };
});
var learningStepFieldsSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected learning step fields object" }] };
  const { learningStep } = value;
  if (learningStep === void 0) return { value: { learningStep: 0 } };
  if (typeof learningStep !== "number" || !Number.isSafeInteger(learningStep) || learningStep < 0) return { issues: [{ message: "Expected non-negative integer learningStep" }] };
  return { value: { learningStep } };
});
function calculateScheduleDays(candidates, maximumInterval) {
  const first = Math.min(candidates[0], maximumInterval);
  if (candidates.length === 1) return [first];
  const second = Math.min(Math.max(candidates[1], first === 0 ? 0 : first + 1), maximumInterval);
  if (candidates.length === 2) return [first, second];
  const third = Math.min(Math.max(candidates[2], second === 0 ? 0 : second + 1), maximumInterval);
  if (candidates.length === 3) return [
    first,
    second,
    third
  ];
  return [
    first,
    second,
    third,
    Math.min(Math.max(candidates[3], third === 0 ? 0 : third + 1), maximumInterval)
  ];
}
var SECONDS_PER_DAY = 86400;
var toSeconds = (days) => Math.round(days * SECONDS_PER_DAY);
function calculateScheduleDay(candidates, maximumInterval) {
  let scheduledDay;
  let subDay = candidates[0];
  for (let index = 0; index < candidates.length; index++) {
    const interval = candidates[index];
    if (interval >= 1) scheduledDay = Math.min(scheduledDay === void 0 ? interval : Math.max(interval, scheduledDay + 1), maximumInterval);
    else if (scheduledDay === void 0 && index > 0) {
      const raised = Math.max(interval, subDay);
      subDay = subDay > 0 && toSeconds(interval) >= toSeconds(candidates[index - 1]) && toSeconds(raised) === toSeconds(subDay) ? subDay + 1 / SECONDS_PER_DAY : raised;
    }
  }
  return scheduledDay ?? subDay;
}
var COST_ADR_DEFAULT_GOAL_COST_WEIGHT = 64;
var COST_ADR_DEFAULT_POLICY = Object.freeze({
  coefficients: Object.freeze([
    -0.202,
    9.14,
    -0.0978,
    0.226,
    -5.31,
    -7.44,
    24.1,
    -0.375,
    1.81,
    -22.9,
    -5.82,
    22.3,
    1.72,
    -1.99,
    -19.4
  ]),
  costWeightMin: 0,
  costWeightMax: 1024,
  retentionMin: 0.3,
  retentionMax: 0.995,
  bounds: Object.freeze({
    sMin: 1e-4,
    sMax: 36500,
    dMin: 1,
    dMax: 10
  })
});
function evaluateCostAdrRetention(policy, memoryState, costWeight) {
  const { bounds, coefficients } = policy;
  const stability = clamp(memoryState.stability, bounds.sMin, bounds.sMax);
  const difficulty = clamp(memoryState.difficulty, bounds.dMin, bounds.dMax);
  const logMin = Math.log(bounds.sMin);
  const xs = clamp((Math.log(stability) - logMin) / (Math.log(bounds.sMax) - logMin), 0, 1);
  const xd = clamp((difficulty - bounds.dMin) / (bounds.dMax - bounds.dMin), 0, 1);
  const weight = clamp(costWeight, policy.costWeightMin, policy.costWeightMax);
  const logWeightMin = Math.log1p(policy.costWeightMin);
  const z = clamp((Math.log1p(weight) - logWeightMin) / (Math.log1p(policy.costWeightMax) - logWeightMin), 0, 1);
  const features = [
    1,
    xs,
    xd,
    xs * xd,
    xs * xs
  ];
  const dot = (offset) => features.reduce((sum, feature, index) => sum + coefficients[offset + index] * feature, 0);
  const value = dot(0) - softplus(dot(5)) * z - softplus(dot(10)) * z * z;
  const exp = Math.exp(-Math.abs(value));
  const sigmoid = value >= 0 ? 1 / (1 + exp) : exp / (1 + exp);
  return clamp(policy.retentionMin + (policy.retentionMax - policy.retentionMin) * sigmoid, policy.retentionMin, policy.retentionMax);
}
function softplus(value) {
  if (value > 20) return value;
  if (value < -20) return Math.exp(value);
  return Math.log1p(Math.exp(value));
}
var costAdrPolicySchema = defineSchema((value) => {
  if (!isObject2(value) || !isNumberArray(value.coefficients) || value.coefficients.length !== 15 || value.coefficients.some((coefficient) => coefficient < -64 || coefficient > 64) || !isFiniteNumber(value.costWeightMin) || !isFiniteNumber(value.costWeightMax) || value.costWeightMin < 0 || value.costWeightMax <= value.costWeightMin || Math.log1p(value.costWeightMax) <= Math.log1p(value.costWeightMin) || !isFiniteNumber(value.retentionMin) || !isFiniteNumber(value.retentionMax) || value.retentionMin <= 0 || value.retentionMax <= value.retentionMin || value.retentionMax >= 1) return { issues: [{ message: "Expected valid Cost ADR policy" }] };
  const { bounds } = value;
  if (!isObject2(bounds) || !isFiniteNumber(bounds.sMin) || !isFiniteNumber(bounds.sMax) || !isFiniteNumber(bounds.dMin) || !isFiniteNumber(bounds.dMax) || bounds.sMin <= 0 || bounds.sMax <= bounds.sMin || Math.log(bounds.sMax) <= Math.log(bounds.sMin) || bounds.dMax <= bounds.dMin || !Number.isFinite(bounds.dMax - bounds.dMin)) return { issues: [{ message: "Expected valid Cost ADR bounds" }] };
  return { value: {
    coefficients: Array.from(value.coefficients),
    costWeightMin: value.costWeightMin,
    costWeightMax: value.costWeightMax,
    retentionMin: value.retentionMin,
    retentionMax: value.retentionMax,
    bounds: {
      sMin: bounds.sMin,
      sMax: bounds.sMax,
      dMin: bounds.dMin,
      dMax: bounds.dMax
    }
  } };
});
var costAdrConfigSchema = defineSchema((value) => {
  if (!isObject2(value) || !isFiniteNumber(value.goalCostWeight) || value.goalCostWeight < 0 || value.goalCostWeight > 1024) return { issues: [{ message: "Expected finite goalCostWeight in [0, 1024]" }] };
  const policy = costAdrPolicySchema["~standard"].validate(value.costAdrPolicy);
  if (policy.issues) return policy;
  return { value: {
    costAdrPolicy: policy.value,
    goalCostWeight: value.goalCostWeight
  } };
});
var costAdrRetentionsSymbol = Symbol("ts-fsrs.cost-adr.retentions");
var schedulerCostAdrMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.cost-adr"),
  schema: { config: costAdrConfigSchema },
  handlers: { nextInterval(ctx, next) {
    const { costAdrPolicy, goalCostWeight } = ctx.config;
    const candidate = ctx.candidate;
    candidate[costAdrRetentionsSymbol] ??= {
      retentions: candidate.desiredRetention,
      lastGrade: 0
    };
    const cached = candidate[costAdrRetentionsSymbol];
    for (const grade of grades) {
      if (grade > ctx.input.grade) break;
      if (grade <= cached.lastGrade) continue;
      cached.retentions[grade] = evaluateCostAdrRetention(costAdrPolicy, parse(FSRSMemoryStateSchema, candidate.step(grade)), goalCostWeight);
      cached.lastGrade = grade;
    }
    next();
  } }
});
var desiredRetentionConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected desiredRetention in (0, 1)" }] };
  const retention = value.desiredRetention;
  const desiredRetention = {};
  if (typeof retention === "number") {
    const result = desiredRetentionSchema.safeParse(retention);
    if (!result.success) return { issues: [{ message: "Expected desiredRetention in (0, 1)" }] };
    for (const grade of grades) desiredRetention[grade] = result.data;
  } else {
    if (!isObject2(retention)) return { issues: [{ message: "Expected desiredRetention in (0, 1)" }] };
    for (const grade of grades) {
      const result = desiredRetentionSchema.safeParse(retention[grade]);
      if (!result.success) return { issues: [{ message: "Expected desiredRetention in (0, 1)" }] };
      desiredRetention[grade] = result.data;
    }
  }
  return { value: { desiredRetention } };
});
var retentionInjectedSymbol = Symbol("ts-fsrs.desired-retention.injected");
var schedulerDesiredRetentionMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.desired-retention"),
  schema: { config: desiredRetentionConfigSchema },
  handlers: { nextInterval(ctx, next) {
    const candidate = ctx.candidate;
    if (ctx.input.desiredRetention === void 0 && !candidate[retentionInjectedSymbol]) {
      for (const grade of grades) candidate.desiredRetention[grade] = ctx.config.desiredRetention[grade];
      candidate[retentionInjectedSymbol] = true;
    }
    next();
  } }
});
function createCardId() {
  const crypto = globalThis.crypto;
  if (typeof crypto?.randomUUID === "function") return crypto.randomUUID();
  const bytes = /* @__PURE__ */ new Uint8Array(16);
  if (typeof crypto?.getRandomValues === "function") crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = bytes[6] & 15 | 64;
  bytes[8] = bytes[8] & 63 | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function parseCardId(value) {
  if (typeof value === "string" && value.length > 0) return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
}
var fuzzingConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected fuzzing config object" }] };
  const { enableFuzz, maximumInterval } = value;
  if (typeof enableFuzz !== "boolean") return { issues: [{ message: "Expected enableFuzz boolean" }] };
  if (typeof maximumInterval !== "number" || !Number.isSafeInteger(maximumInterval) || maximumInterval <= 0) return { issues: [{ message: "Expected positive integer maximumInterval" }] };
  const fractional = fractionalDaysConfigSchema["~standard"].validate(value);
  if (fractional.issues) return fractional;
  return { value: {
    enableFuzz,
    maximumInterval,
    fractionalDays: fractional.value.fractionalDays
  } };
});
var fuzzingCardInitInputSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected fuzzing card init input object" }] };
  if (value.cardId === void 0) return { value: {} };
  const cardId = parseCardId(value.cardId);
  return cardId === void 0 ? { issues: [{ message: "Expected new card cardId" }] } : { value: { cardId } };
});
var fuzzingCardFieldsSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected card cardId" }] };
  const cardId = parseCardId(value.cardId);
  if (cardId === void 0) return { issues: [{ message: "Expected card cardId" }] };
  const { reps } = value;
  if (typeof reps !== "number" || !Number.isSafeInteger(reps) || reps < 0) return { issues: [{ message: "Expected non-negative integer reps" }] };
  return { value: {
    cardId,
    reps
  } };
});
var fuzzingRevlogFieldsSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected revlog cardId" }] };
  const cardId = parseCardId(value.cardId);
  return cardId === void 0 ? { issues: [{ message: "Expected revlog cardId" }] } : { value: { cardId } };
});
var fuzzingDecoratorSymbol = Symbol("ts-fsrs.fuzzing.decorator");
function createSchedulerFuzzingMiddleware(options = {}) {
  const { fuzzingRange = FUZZ_RANGES, rng = fnv1aMulberry32Rng } = options;
  function decorateInterval(ctx, reps) {
    if (!ctx.config.enableFuzz) return;
    const card = ctx.input.card;
    const candidate = ctx.candidate;
    if (!candidate[fuzzingDecoratorSymbol]) {
      const nextInterval = candidate.nextInterval;
      const seed = `${card.cardId}${reps}`;
      candidate.nextInterval = (memoryState, desiredRetention) => {
        const interval = nextInterval(memoryState, desiredRetention);
        if (interval < 2.5) return ctx.config.fractionalDays ? interval : Math.round(interval);
        const { minInterval, maxInterval } = getFuzzRange(interval, ctx.elapsedDays, ctx.config.maximumInterval, fuzzingRange);
        const fuzzFactor = rng(seed)();
        return Math.floor(fuzzFactor * (maxInterval - minInterval + 1) + minInterval);
      };
      candidate[fuzzingDecoratorSymbol] = true;
    }
  }
  return defineMiddleware({
    name: Symbol("ts-fsrs.fuzzing"),
    schema: {
      config: fuzzingConfigSchema,
      cardInitInput: fuzzingCardInitInputSchema,
      card: fuzzingCardFieldsSchema,
      revlog: fuzzingRevlogFieldsSchema
    },
    defaultValue: { card(ctx) {
      if (ctx.operation === "forget") return {
        cardId: ctx.input.cardId,
        reps: ctx.config.clearStatsOnForget === false ? ctx.input.reps : 0
      };
      return {
        cardId: ctx.input.cardId ?? createCardId(),
        reps: 0
      };
    } },
    handlers: {
      nextInterval(ctx, next) {
        decorateInterval(ctx, ctx.input.card.reps + 1);
        if (ctx.config.enableFuzz) ctx.scheduledDays = void 0;
        next();
      },
      review(ctx, next) {
        const card = ctx.input.card;
        if (!ctx.config.enableFuzz) {
          next();
          ctx.result.card.cardId = card.cardId;
          ctx.result.card.reps ??= card.reps + 1;
          ctx.result.revlog.cardId = card.cardId;
          return;
        }
        const reps = ctx.result.card.reps ?? card.reps + 1;
        decorateInterval(ctx, reps);
        next();
        ctx.result.card.cardId = card.cardId;
        ctx.result.card.reps ??= reps;
        ctx.result.revlog.cardId = card.cardId;
      },
      rollback(ctx, next) {
        next();
        ctx.result.card.cardId = ctx.input.revlog.cardId;
        ctx.result.card.reps ??= Math.max(0, ctx.input.card.reps - 1);
      }
    }
  });
}
var schedulerFuzzingMiddleware = createSchedulerFuzzingMiddleware();
var MINUTES_PER_DAY = 1440;
var SECONDS_PER_MINUTE = 60;
var resolvedStepsSymbol = Symbol("ts-fsrs.learning-steps.resolved");
var schedulerLearningStepsMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.learning-steps"),
  schema: {
    config: learningStepsConfigSchema,
    card: learningStepFieldsSchema,
    revlog: learningStepFieldsSchema
  },
  defaultValue: { card() {
    return { learningStep: 0 };
  } },
  handlers: {
    nextInterval: scheduleLearningSteps,
    review(ctx, next) {
      const resolved = ctx.config.enableShortTerm ? resolveLearningSteps(ctx) : void 0;
      next();
      const { card, grade } = ctx.input;
      const { graduatingInterval } = ctx.config;
      const scheduledDays = ctx.scheduledDays;
      const step = resolved?.stepIntervals[grade] !== void 0 ? resolved.steps[grade] : void 0;
      ctx.result.revlog.learningStep = card.learningStep;
      ctx.result.card.learningStep = 0;
      if (grade === Rating.Again && resolved?.overridesStep[grade] === true || scheduledDays !== void 0 && scheduledDays < graduatingInterval) {
        ctx.result.card.state = nextLearningState(card.state);
        ctx.result.card.scheduleStatus = "learning";
        if (step) ctx.result.card.learningStep = Math.max(0, step.nextStep);
      }
    },
    rollback(ctx, next) {
      next();
      ctx.result.card.learningStep = ctx.input.revlog.learningStep;
    }
  }
});
function scheduleLearningSteps(ctx, next) {
  if (!ctx.config.enableShortTerm) {
    next();
    return;
  }
  const resolved = resolveLearningSteps(ctx);
  next();
  const { grade } = ctx.input;
  const stepInterval = resolved.stepIntervals[grade];
  if (stepInterval !== void 0 && !resolved.overridesStep[grade]) ctx.scheduledDays = stepInterval;
  return resolved;
}
function resolveLearningSteps(ctx) {
  const candidate = ctx.candidate;
  const cached = candidate[resolvedStepsSymbol];
  if (cached) return cached;
  const { card } = ctx.input;
  const { config } = ctx;
  const stepList = card.state === State.Relearning || card.state === State.Review ? config.relearningSteps : config.learningSteps;
  const steps = calculateLearningSteps(config, card.state, card.learningStep);
  const stepIntervals = {};
  for (const grade of grades) {
    const step = steps[grade];
    if (!step) continue;
    const minutes = Math.round(Math.max(0, step.scheduledMinutes) * SECONDS_PER_MINUTE) / SECONDS_PER_MINUTE;
    if (minutes > 0) stepIntervals[grade] = minutes / MINUTES_PER_DAY;
  }
  const resolved = {
    steps,
    hasSteps: stepList.length > 0,
    stepIntervals,
    overridesStep: {}
  };
  candidate[resolvedStepsSymbol] = resolved;
  const nextInterval = candidate.nextInterval;
  candidate.nextInterval = (memoryState, desiredRetention) => {
    const grade = candidate.findGrade(memoryState);
    if (grade === void 0) return nextInterval(memoryState, desiredRetention);
    const interval = getLearningStepInterval(resolved, grade, config, () => nextInterval(memoryState, desiredRetention));
    const stepInterval = resolved.stepIntervals[grade];
    resolved.overridesStep[grade] = stepInterval !== void 0 && interval !== stepInterval;
    return interval;
  };
  return resolved;
}
function getLearningStepInterval(resolved, grade, { allowModelOverride, graduatingInterval }, modelInterval) {
  const stepInterval = resolved.stepIntervals[grade];
  switch (grade) {
    case Rating.Again:
      if (stepInterval === void 0) return modelInterval();
      return allowModelOverride ? Math.max(stepInterval, Math.min(modelInterval(), graduatingInterval)) : stepInterval;
    default:
      if (stepInterval === void 0) return resolved.hasSteps ? Math.max(modelInterval(), graduatingInterval) : modelInterval();
      return allowModelOverride ? Math.max(stepInterval, modelInterval()) : stepInterval;
  }
}
function nextLearningState(state) {
  if (state === State.New) return State.Learning;
  if (state === State.Review) return State.Relearning;
  return state;
}
var DEFAULT_LEECH_THRESHOLD = 0;
var leechConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected leech config object" }] };
  const leechThreshold = value.leechThreshold === void 0 ? 0 : value.leechThreshold;
  if (typeof leechThreshold !== "number" || !Number.isSafeInteger(leechThreshold) || leechThreshold < 0) return { issues: [{ message: "Expected non-negative integer leechThreshold" }] };
  return { value: { leechThreshold } };
});
var leechCardFieldsSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected leech card fields" }] };
  const { lapses } = value;
  if (typeof lapses !== "number" || !Number.isSafeInteger(lapses) || lapses < 0) return { issues: [{ message: "Expected non-negative integer lapses" }] };
  return { value: { lapses } };
});
var schedulerLeechMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.leech"),
  scheduleStatus: ["suspended"],
  schema: {
    config: leechConfigSchema,
    card: leechCardFieldsSchema
  },
  defaultValue: { card(ctx) {
    return { lapses: ctx.operation === "forget" && ctx.config.clearStatsOnForget === false ? ctx.input.lapses : 0 };
  } },
  handlers: {
    review(ctx, next) {
      next();
      const card = ctx.input.card;
      const isLapse = card.state === State.Review && ctx.input.grade === Rating.Again;
      ctx.result.card.lapses ??= isLapse ? card.lapses + 1 : card.lapses;
      const { lapses } = ctx.result.card;
      const { leechThreshold } = ctx.config;
      if (isLapse && leechThreshold > 0 && lapses % leechThreshold === 0) ctx.result.card.scheduleStatus = "suspended";
    },
    rollback(ctx, next) {
      next();
      const card = ctx.input.card;
      const revlog = ctx.input.revlog;
      const isLapse = revlog.rating === Rating.Again && revlog.state === State.Review;
      ctx.result.card.lapses ??= Math.max(0, card.lapses - (isLapse ? 1 : 0));
    }
  }
});
var DEFAULT_MAXIMUM_INTERVAL = 36500;
var monotonicIntervalConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected monotonic interval config" }] };
  const maximumInterval = value.maximumInterval === void 0 ? DEFAULT_MAXIMUM_INTERVAL : value.maximumInterval;
  if (typeof maximumInterval !== "number" || !Number.isSafeInteger(maximumInterval) || maximumInterval <= 0) return { issues: [{ message: "Expected positive integer maximumInterval" }] };
  return { value: { maximumInterval } };
});
var schedulerMaximumIntervalMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.maximum-interval"),
  schema: { config: monotonicIntervalConfigSchema },
  handlers: { nextInterval(ctx, next) {
    next();
    if (ctx.scheduledDays !== void 0) ctx.scheduledDays = Math.min(ctx.scheduledDays, ctx.config.maximumInterval);
  } }
});
var schedulerMonotonicIntervalMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.monotonic-interval"),
  schema: { config: monotonicIntervalConfigSchema },
  handlers: { nextInterval(ctx, next) {
    const { grade } = ctx.input;
    const interval = (rating) => ctx.candidate.nextInterval(ctx.candidate.step(rating), parse(desiredRetentionSchema, ctx.candidate.desiredRetention[rating]));
    const schedule = (...candidates) => calculateScheduleDay(candidates, ctx.config.maximumInterval);
    next();
    const scheduledDays = ctx.scheduledDays;
    switch (grade) {
      case Rating.Again:
        ctx.scheduledDays = schedule(scheduledDays);
        break;
      case Rating.Hard:
        ctx.scheduledDays = schedule(interval(Rating.Again), scheduledDays);
        break;
      case Rating.Good:
        ctx.scheduledDays = schedule(interval(Rating.Again), interval(Rating.Hard), scheduledDays);
        break;
      case Rating.Easy:
        ctx.scheduledDays = schedule(interval(Rating.Again), interval(Rating.Hard), interval(Rating.Good), scheduledDays);
    }
  } }
});
var scheduledDaysFieldsSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected object with scheduledDays" }] };
  const scheduledDays = scheduledDaysSchema.safeParse(value.scheduledDays);
  if (!scheduledDays.success) return scheduledDays;
  return { value: { scheduledDays: scheduledDays.data } };
});
var schedulerScheduledDaysMiddleware = defineMiddleware({
  name: Symbol("ts-fsrs.scheduled-days"),
  schema: {
    config: fractionalDaysConfigSchema,
    card: scheduledDaysFieldsSchema,
    revlog: scheduledDaysFieldsSchema
  },
  defaultValue: { card() {
    return { scheduledDays: 0 };
  } },
  handlers: {
    review(ctx, next) {
      const previousScheduledDays = ctx.input.card.scheduledDays;
      next();
      const days = Math.max(0, ctx.scheduledDays ?? 0);
      ctx.result.card.scheduledDays = ctx.config.fractionalDays ? days : Math.floor(days);
      ctx.result.revlog.scheduledDays = previousScheduledDays;
    },
    rollback(ctx, next) {
      next();
      ctx.result.card.scheduledDays = ctx.input.revlog.scheduledDays;
    }
  }
});

// node_modules/ts-fsrs/dist/index.mjs
init_constants_YU7EeO_L();
init_fsrs_6_Bt0f3F6X();
init_esm();

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/chrono/date/index.js
init_schema_CgTDED3c();
init_define_chrono_DVqT65EB();
var MS_PER_DAY = 864e5;
function isValidDate2(value) {
  return dateSchema.safeParse(value).success;
}
function invalidDateFields() {
  return { issues: [{ message: "Expected valid Date fields" }] };
}
var dateCardFieldsSchema = defineSchema((value) => {
  if (!isObject2(value) || !("dueAt" in value)) return invalidDateFields();
  const { dueAt, lastReviewAt } = value;
  if (!isValidDate2(dueAt)) return invalidDateFields();
  if (lastReviewAt !== void 0 && lastReviewAt !== null && !isValidDate2(lastReviewAt)) return invalidDateFields();
  return { value: {
    dueAt,
    lastReviewAt: lastReviewAt !== void 0 ? lastReviewAt : null
  } };
});
var dateRevlogFieldsSchema = defineSchema((value) => {
  if (!isObject2(value) || !("reviewTime" in value)) return invalidDateFields();
  const card = dateCardFieldsSchema["~standard"].validate(value);
  if (card.issues) return card;
  const { reviewTime } = value;
  if (!isValidDate2(reviewTime)) return invalidDateFields();
  const revlog = card.value;
  revlog.reviewTime = reviewTime;
  return { value: revlog };
});
var differenceByMode = {
  elapsed: elapsedUtcDays,
  calendar: dateDiffInDays
};
var dateChrono = defineChrono({
  schema: {
    config: fractionalDaysConfigSchema,
    card: dateCardFieldsSchema,
    revlog: dateRevlogFieldsSchema,
    time: dateSchema
  },
  normalize(value) {
    if (!isObject2(value)) return { issues: [{ message: "Expected valid Date fields" }] };
    if ("card" in value) {
      const card = dateCardFieldsSchema["~standard"].validate(value.card);
      if (card.issues) return card;
      const time = dateSchema["~standard"].validate(value.time);
      if (time.issues) return time;
      return { value: {
        previous: card.value.lastReviewAt,
        current: card.value.dueAt
      } };
    }
    const revlog = dateRevlogFieldsSchema["~standard"].validate(value.revlog);
    if (revlog.issues) return revlog;
    return { value: {
      previous: revlog.value.lastReviewAt,
      current: revlog.value.dueAt
    } };
  },
  defaultValue: {
    card({ previous, time }) {
      return {
        dueAt: time,
        lastReviewAt: previous ?? null
      };
    },
    revlog({ time, previous }) {
      return {
        dueAt: time,
        lastReviewAt: previous?.previous ?? null,
        reviewTime: previous?.current ?? time
      };
    }
  },
  create({ config }) {
    const differenceMode = config.fractionalDays ? "elapsed" : "calendar";
    const difference2 = differenceByMode[differenceMode];
    return {
      now,
      compare,
      difference: difference2,
      add
    };
  }
});
var now = () => /* @__PURE__ */ new Date();
var compare = (left, right) => {
  const leftTime = left.getTime();
  const rightTime = right.getTime();
  return leftTime < rightTime ? -1 : leftTime > rightTime ? 1 : 0;
};
var add = (from, days) => new Date(from.getTime() + days * MS_PER_DAY);
function elapsedUtcDays(from, to) {
  return (to.getTime() - from.getTime()) / MS_PER_DAY;
}
function dateDiffInDays(last, cur) {
  const utc1 = Date.UTC(last.getUTCFullYear(), last.getUTCMonth(), last.getUTCDate());
  const utc2 = Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth(), cur.getUTCDate());
  return Math.floor((utc2 - utc1) / MS_PER_DAY);
}

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/chrono/numeric/index.js
init_schema_CgTDED3c();
init_define_chrono_DVqT65EB();
var numericTimeNormalizer = defineChronoTimeNormalizer((value) => {
  const time = numberSchema["~standard"].validate(value.time);
  if (time.issues) return time;
  return { value: {
    previous: 0,
    current: time.value
  } };
});
var numericChrono = defineChrono({
  schema: { time: numberSchema },
  normalize: numericTimeNormalizer,
  create() {
    return {
      now: now2,
      difference,
      add: add2
    };
  }
});
var now2 = () => 0;
var difference = (from, to) => to - from;
var add2 = (from, days) => from + days;

// node_modules/@open-spaced-repetition/srs-kit/dist/esm/chrono/temporal-instant/index.js
init_schema_CgTDED3c();
init_define_chrono_DVqT65EB();
function getTemporalInstantConstructor() {
  const temporal = globalThis.Temporal;
  if (temporal?.Instant === void 0) throw new ReferenceError("Temporal.Instant is not available in this runtime. Install a Temporal polyfill or upgrade to Node.js 26+ for native Temporal support. See https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal#browser_compatibility");
  return temporal.Instant;
}
var UTC_OFFSET_RE = /^[+-](?:[01]\d|2[0-3]):[0-5]\d$/;
function parseTimeZoneId(timezone) {
  if (timezone === "UTC" || UTC_OFFSET_RE.test(timezone)) return timezone;
  try {
    return getTemporalInstantConstructor().fromEpochNanoseconds(0n).toZonedDateTimeISO(timezone).timeZoneId;
  } catch {
    return;
  }
}
var temporalInstantConfigSchema = defineSchema((value) => {
  if (!isObject2(value)) return { issues: [{ message: "Expected temporal instant config" }] };
  const timezone = value.timezone === void 0 ? "UTC" : value.timezone;
  if (typeof timezone !== "string") return { issues: [{ message: "Expected timezone to be a string" }] };
  const timezoneId = parseTimeZoneId(timezone);
  if (timezoneId === void 0) return { issues: [{ message: "Expected valid timezone" }] };
  const fractional = fractionalDaysConfigSchema["~standard"].validate(value);
  if (fractional.issues) return fractional;
  return { value: {
    timezone: timezoneId,
    fractionalDays: fractional.value.fractionalDays
  } };
});
var temporalInstantSchema = defineSchema((value) => {
  return value instanceof getTemporalInstantConstructor() ? { value } : { issues: [{ message: "Expected Temporal.Instant" }] };
});
function invalidInstantFields() {
  return { issues: [{ message: "Expected Temporal.Instant fields" }] };
}
var temporalInstantCardFieldsSchema = defineSchema((value) => {
  if (!isObject2(value) || !("dueAt" in value)) return invalidInstantFields();
  const dueAt = temporalInstantSchema.safeParse(value.dueAt);
  if (!dueAt.success) return invalidInstantFields();
  if (value.lastReviewAt === void 0 || value.lastReviewAt === null) return { value: {
    dueAt: dueAt.data,
    lastReviewAt: null
  } };
  const lastReviewAt = temporalInstantSchema.safeParse(value.lastReviewAt);
  if (!lastReviewAt.success) return invalidInstantFields();
  return { value: {
    dueAt: dueAt.data,
    lastReviewAt: lastReviewAt.data
  } };
});
var temporalInstantRevlogFieldsSchema = defineSchema((value) => {
  if (!isObject2(value) || !("reviewTime" in value)) return invalidInstantFields();
  const card = temporalInstantCardFieldsSchema["~standard"].validate(value);
  if (card.issues) return card;
  const reviewTime = temporalInstantSchema.safeParse(value.reviewTime);
  if (!reviewTime.success) return invalidInstantFields();
  const revlog = card.value;
  revlog.reviewTime = reviewTime.data;
  return { value: revlog };
});
var MS_PER_DAY2 = 864e5;
function utcDateDifferenceInDays(from, to) {
  const fromDate = from.toZonedDateTimeISO("UTC").toPlainDate();
  const toDate = to.toZonedDateTimeISO("UTC").toPlainDate();
  return fromDate.until(toDate, { largestUnit: "day" }).days;
}
function addFixedUtcDays(from, days) {
  return from.add({ milliseconds: Math.round(days * MS_PER_DAY2) });
}
var NS_PER_MS = 1000000n;
var differenceByMode2 = {
  fractional: fractionalZonedDifferenceInDays,
  utc: utcDateDifferenceInDays,
  zoned: zonedDateDifferenceInDays
};
var addByMode = {
  utc: addFixedUtcDays,
  zoned: addZonedCalendarDays
};
var temporalInstantChrono = defineChrono({
  schema: {
    config: temporalInstantConfigSchema,
    card: temporalInstantCardFieldsSchema,
    revlog: temporalInstantRevlogFieldsSchema,
    time: temporalInstantSchema
  },
  normalize(value) {
    if (!isObject2(value)) return { issues: [{ message: "Expected Temporal.Instant fields" }] };
    if ("card" in value) {
      const card = temporalInstantCardFieldsSchema["~standard"].validate(value.card);
      if (card.issues) return card;
      const time = temporalInstantSchema["~standard"].validate(value.time);
      if (time.issues) return time;
      return { value: {
        previous: card.value.lastReviewAt,
        current: card.value.dueAt
      } };
    }
    const revlog = temporalInstantRevlogFieldsSchema["~standard"].validate(value.revlog);
    if (revlog.issues) return revlog;
    return { value: {
      previous: revlog.value.lastReviewAt,
      current: revlog.value.dueAt
    } };
  },
  defaultValue: {
    card({ previous, time }) {
      return {
        dueAt: time,
        lastReviewAt: previous ?? null
      };
    },
    revlog({ time, previous }) {
      return {
        dueAt: time,
        lastReviewAt: previous?.previous ?? null,
        reviewTime: previous?.current ?? time
      };
    }
  },
  create({ config }) {
    getTemporalInstantConstructor();
    const { fractionalDays, timezone } = config;
    const addMode = timezone === "UTC" ? "utc" : "zoned";
    const differenceMode = fractionalDays ? "fractional" : addMode;
    return {
      now: now3,
      compare: compare2,
      difference: (from, to) => differenceByMode2[differenceMode](from, to, timezone),
      add: (from, days) => addByMode[addMode](from, days, timezone)
    };
  }
});
var now3 = () => Temporal.Now.instant();
function compare2(left, right) {
  if (left.epochNanoseconds < right.epochNanoseconds) return -1;
  if (left.epochNanoseconds > right.epochNanoseconds) return 1;
  return 0;
}
function zonedDateDifferenceInDays(from, to, timezone) {
  const fromDate = from.toZonedDateTimeISO(timezone).toPlainDate();
  const toDate = to.toZonedDateTimeISO(timezone).toPlainDate();
  return fromDate.until(toDate, { largestUnit: "day" }).days;
}
function fractionalZonedDifferenceInDays(from, to, timezone) {
  const fromZoned = from.toZonedDateTimeISO(timezone);
  const toZoned = to.toZonedDateTimeISO(timezone);
  return fromZoned.until(toZoned, {
    largestUnit: "day",
    smallestUnit: "nanosecond"
  }).total({
    unit: "day",
    relativeTo: fromZoned
  });
}
function addZonedCalendarDays(from, days, timezone) {
  const whole = Math.trunc(days);
  const fraction = days - whole;
  const shifted = from.toZonedDateTimeISO(timezone).add({ days: whole });
  if (fraction === 0) return shifted.toInstant();
  const neighbor = shifted.add({ days: fraction > 0 ? 1 : -1 });
  const dayLengthMs = Math.abs(Number((neighbor.epochNanoseconds - shifted.epochNanoseconds) / NS_PER_MS));
  const milliseconds = Math.round(Math.abs(fraction) * dayLengthMs) * Math.sign(fraction);
  return shifted.add({ milliseconds }).toInstant();
}

// node_modules/ts-fsrs/dist/index.mjs
var TypeConvert = class TypeConvert2 {
  /** @deprecated Map legacy card fields to the selected scheduler's card input and deserialize dates explicitly. */
  static card(card) {
    return {
      ...card,
      state: TypeConvert2.state(card.state),
      due: TypeConvert2.time(card.due),
      last_review: card.last_review ? TypeConvert2.time(card.last_review) : void 0
    };
  }
  /** @deprecated Use ratingSchema for numeric values; map string labels explicitly before validation. */
  static rating(value) {
    if (typeof value === "string") {
      const firstLetter = value.charAt(0).toUpperCase();
      const restOfString = value.slice(1).toLowerCase();
      const ret = Rating[`${firstLetter}${restOfString}`];
      if (ret === void 0) throw new FSRSValidationError(`Invalid rating:[${value}]`);
      return ret;
    } else if (typeof value === "number") return value;
    throw new FSRSValidationError(`Invalid rating:[${value}]`);
  }
  /** @deprecated Use stateSchema for numeric values; map string labels explicitly before validation. */
  static state(value) {
    if (typeof value === "string") {
      const firstLetter = value.charAt(0).toUpperCase();
      const restOfString = value.slice(1).toLowerCase();
      const ret = State[`${firstLetter}${restOfString}`];
      if (ret === void 0) throw new FSRSValidationError(`Invalid state:[${value}]`);
      return ret;
    } else if (typeof value === "number") return value;
    throw new FSRSValidationError(`Invalid state:[${value}]`);
  }
  /** @deprecated Use new Date(value) for supported serialized inputs and reject invalid dates before passing them to dateChrono. */
  static time(value) {
    if (value instanceof Date) return value;
    const date = new Date(value);
    if (typeof value === "object" && value !== null && !Number.isNaN(Date.parse(value) || +date)) return date;
    else if (typeof value === "string") {
      const timestamp = Date.parse(value);
      if (!Number.isNaN(timestamp)) return new Date(timestamp);
      else throw new FSRSValidationError(`Invalid date:[${value}]`);
    } else if (typeof value === "number") return new Date(value);
    throw new FSRSValidationError(`Invalid date:[${value}]`);
  }
  /** @deprecated Map review logs to the selected scheduler's revlog input; preserve pre-review timestamps for rollback. */
  static review_log(log) {
    return {
      ...log,
      due: TypeConvert2.time(log.due),
      rating: TypeConvert2.rating(log.rating),
      state: TypeConvert2.state(log.state),
      review: TypeConvert2.time(log.review)
    };
  }
};
function date_scheduler(now4, t, isDay) {
  return new Date(isDay ? TypeConvert.time(now4).getTime() + t * 24 * 60 * 60 * 1e3 : TypeConvert.time(now4).getTime() + t * 60 * 1e3);
}
function date_diff(now4, pre, unit) {
  if (!now4 || !pre) throw new FSRSValidationError("Invalid date");
  const diff = TypeConvert.time(now4).getTime() - TypeConvert.time(pre).getTime();
  let r = 0;
  switch (unit) {
    case "days":
      r = Math.floor(diff / 864e5);
      break;
    case "minutes":
      r = Math.floor(diff / 6e4);
  }
  return r;
}
function formatDate(dateInput) {
  const date = TypeConvert.time(dateInput);
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();
  return `${year}-${padZero(month)}-${padZero(day)} ${padZero(hours)}:${padZero(minutes)}:${padZero(seconds)}`;
}
function padZero(num) {
  return num < 10 ? `0${num}` : `${num}`;
}
var TIMEUNIT = [
  60,
  60,
  24,
  31,
  12
];
var TIMEUNITFORMAT = [
  "second",
  "min",
  "hour",
  "day",
  "month",
  "year"
];
function show_diff_message(due, last_review, unit, timeUnit = TIMEUNITFORMAT) {
  due = TypeConvert.time(due);
  last_review = TypeConvert.time(last_review);
  if (timeUnit.length !== TIMEUNITFORMAT.length) timeUnit = TIMEUNITFORMAT;
  let diff = due.getTime() - last_review.getTime();
  let i = 0;
  diff /= 1e3;
  for (i = 0; i < TIMEUNIT.length; i++) {
    if (diff < TIMEUNIT[i]) break;
    diff /= TIMEUNIT[i];
  }
  return `${Math.floor(diff)}${unit ? timeUnit[i] : ""}`;
}
var Grades = Object.freeze([
  Rating.Again,
  Rating.Hard,
  Rating.Good,
  Rating.Easy
]);
function get_fuzz_range(interval, elapsed_days, maximum_interval) {
  const { minInterval, maxInterval } = getFuzzRange(interval, elapsed_days, maximum_interval);
  return {
    min_ivl: minInterval,
    max_ivl: maxInterval
  };
}
function dateDiffInDays2(last, cur) {
  const utc1 = Date.UTC(last.getUTCFullYear(), last.getUTCMonth(), last.getUTCDate());
  const utc2 = Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth(), cur.getUTCDate());
  return Math.floor((utc2 - utc1) / 864e5);
}
var AbstractScheduler = class {
  last;
  current;
  review_time;
  next = /* @__PURE__ */ new Map();
  model;
  parameters;
  strategies;
  elapsed_days = 0;
  _seed;
  /** @deprecated Use defineScheduler(...).create({ config }). */
  constructor(card, now4, model, parameters, strategies) {
    this.model = model;
    this.parameters = parameters;
    this.last = TypeConvert.card(card);
    this.current = TypeConvert.card(card);
    this.review_time = TypeConvert.time(now4);
    this.strategies = strategies;
    this.init();
  }
  checkGrade(grade) {
    if (!Number.isFinite(grade) || grade < 1 || grade > 4) throw new FSRSValidationError(`Invalid grade "${grade}",expected 1-4`);
  }
  init() {
    const { state, last_review } = this.current;
    let interval = 0;
    if (state !== State.New && last_review) interval = dateDiffInDays2(last_review, this.review_time);
    this.current.last_review = this.review_time;
    this.elapsed_days = interval;
    this.current.reps += 1;
    this._seed = `${this.review_time.getTime()}_${this.current.reps}_${this.current.difficulty * this.current.stability}`;
  }
  /** @deprecated Use scheduler.preview({ card, now }) from the new scheduler API. */
  preview() {
    return {
      [Rating.Again]: this.review(Rating.Again),
      [Rating.Hard]: this.review(Rating.Hard),
      [Rating.Good]: this.review(Rating.Good),
      [Rating.Easy]: this.review(Rating.Easy),
      [Symbol.iterator]: this.previewIterator.bind(this)
    };
  }
  *previewIterator() {
    for (const grade of Grades) yield this.review(grade);
  }
  /** @deprecated Use scheduler.review({ card, now, grade }) from the new scheduler API. */
  review(grade) {
    const { state } = this.last;
    let item;
    this.checkGrade(grade);
    switch (state) {
      case State.New:
        item = this.newState(grade);
        break;
      case State.Learning:
      case State.Relearning:
        item = this.learningState(grade);
        break;
      case State.Review:
        item = this.reviewState(grade);
    }
    return item;
  }
  buildLog(rating) {
    const { last_review, due } = this.last;
    return {
      rating,
      state: this.current.state,
      due: last_review || due,
      stability: this.current.stability,
      difficulty: this.current.difficulty,
      scheduled_days: this.current.scheduled_days,
      learning_steps: this.current.learning_steps,
      review: this.review_time
    };
  }
};
var version = "6.0.0";
var default_request_retention = 0.9;
var default_maximum_interval = 36500;
var default_enable_fuzz = false;
var default_enable_short_term = true;
var FSRSVersion = `v${version}`;
var S_MIN = FSRS6_MODEL_BOUNDS.sMin;
var S_MAX = FSRS6_MODEL_BOUNDS.sMax;
var INIT_S_MAX = 100;
var default_w = FSRS6_DEFAULT_WEIGHTS;
var W17_W18_Ceiling = 2;
var CLAMP_PARAMETERS = FSRS6ParameterBounds;
var checkParameters = (parameters) => {
  if (parameters.find((param) => !Number.isFinite(param)) !== void 0) throw new FSRSValidationError(`Non-finite or NaN value in parameters ${parameters}`);
  else if (![
    17,
    19,
    21
  ].includes(parameters.length)) throw new FSRSValidationError(`Invalid parameter length: ${parameters.length}. Must be 17, 19 or 21 for FSRSv4, 5 and 6 respectively.`);
  return parameters;
};
var generatorParameters = (props) => {
  const learning_steps = Array.isArray(props?.learning_steps) ? props.learning_steps : defaultLearningSteps;
  const relearning_steps = Array.isArray(props?.relearning_steps) ? props.relearning_steps : defaultRelearningSteps;
  const enable_short_term = props?.enable_short_term ?? true;
  const w = migrateFSRS6Parameters(props?.w ? Array.from(props.w) : void 0);
  return {
    request_retention: props?.request_retention || 0.9,
    maximum_interval: props?.maximum_interval || 36500,
    w,
    enable_fuzz: props?.enable_fuzz ?? false,
    enable_short_term,
    learning_steps,
    relearning_steps
  };
};
function createEmptyCard(now4) {
  return {
    due: now4 ? TypeConvert.time(now4) : /* @__PURE__ */ new Date(),
    stability: 0,
    difficulty: 0,
    scheduled_days: 0,
    reps: 0,
    lapses: 0,
    learning_steps: 0,
    state: State.New,
    last_review: void 0
  };
}
var StrategyMode = /* @__PURE__ */ (function(StrategyMode2) {
  StrategyMode2["SCHEDULER"] = "Scheduler";
  StrategyMode2["LEARNING_STEPS"] = "LearningSteps";
  return StrategyMode2;
})({});
var SECONDS_PER_MINUTE2 = 60;
var BasicScheduler = class extends AbstractScheduler {
  learningSteps;
  learningStepsConfig;
  learningStepsResult;
  constructor(card, now4, model, parameters, strategies) {
    super(card, now4, model, parameters, strategies);
    this.learningStepsConfig = {
      learningSteps: parameters.learning_steps,
      relearningSteps: parameters.relearning_steps
    };
    let learningSteps = calculateLearningSteps;
    if (this.strategies) {
      const customStrategy = this.strategies.get("LearningSteps");
      if (customStrategy) learningSteps = customStrategy;
    }
    this.learningSteps = learningSteps;
  }
  getLearningInfo(card, grade) {
    card.learning_steps = card.learning_steps || 0;
    let steps = this.learningStepsResult;
    if (!steps) {
      steps = this.learningSteps(this.learningStepsConfig, card.state, card.learning_steps);
      this.learningStepsResult = steps;
    }
    return {
      scheduled_minutes: Math.round(Math.max(0, steps[grade]?.scheduledMinutes ?? 0) * SECONDS_PER_MINUTE2) / SECONDS_PER_MINUTE2,
      next_steps: Math.max(0, steps[grade]?.nextStep ?? 0)
    };
  }
  /**
  * @description This function applies the learning steps based on the current card's state and grade.
  */
  applyLearningSteps(nextCard, grade, to_state) {
    const { scheduled_minutes, next_steps } = this.getLearningInfo(this.current, grade);
    if (scheduled_minutes > 0 && scheduled_minutes < 1440) {
      nextCard.learning_steps = next_steps;
      nextCard.scheduled_days = 0;
      nextCard.state = to_state;
      nextCard.due = date_scheduler(this.review_time, scheduled_minutes, false);
    } else {
      nextCard.state = State.Review;
      if (scheduled_minutes >= 1440) {
        nextCard.learning_steps = next_steps;
        nextCard.due = date_scheduler(this.review_time, scheduled_minutes, false);
        nextCard.scheduled_days = Math.floor(scheduled_minutes / 1440);
      } else {
        nextCard.learning_steps = 0;
        const interval = this.scheduler_next_interval(nextCard, this.elapsed_days);
        nextCard.scheduled_days = interval;
        nextCard.due = date_scheduler(this.review_time, interval, true);
      }
    }
  }
  newState(grade) {
    const exist = this.next.get(grade);
    if (exist) return exist;
    const next = this.next_ds(this.elapsed_days, grade);
    this.applyLearningSteps(next, grade, State.Learning);
    const item = {
      card: next,
      log: this.buildLog(grade)
    };
    this.next.set(grade, item);
    return item;
  }
  learningState(grade) {
    const exist = this.next.get(grade);
    if (exist) return exist;
    const next = this.next_ds(this.elapsed_days, grade);
    this.applyLearningSteps(next, grade, this.last.state);
    const item = {
      card: next,
      log: this.buildLog(grade)
    };
    this.next.set(grade, item);
    return item;
  }
  reviewState(grade) {
    const exist = this.next.get(grade);
    if (exist) return exist;
    const interval = this.elapsed_days;
    const retrievability = this.model.forgettingCurve(this.current, interval);
    const next_again = this.next_ds(interval, Rating.Again, retrievability);
    const next_hard = this.next_ds(interval, Rating.Hard, retrievability);
    const next_good = this.next_ds(interval, Rating.Good, retrievability);
    const next_easy = this.next_ds(interval, Rating.Easy, retrievability);
    this.next_interval(next_hard, next_good, next_easy, interval);
    this.next_state(next_hard, next_good, next_easy);
    this.applyLearningSteps(next_again, Rating.Again, State.Relearning);
    next_again.lapses += 1;
    const item_again = {
      card: next_again,
      log: this.buildLog(Rating.Again)
    };
    const item_hard = {
      card: next_hard,
      log: super.buildLog(Rating.Hard)
    };
    const item_good = {
      card: next_good,
      log: super.buildLog(Rating.Good)
    };
    const item_easy = {
      card: next_easy,
      log: super.buildLog(Rating.Easy)
    };
    this.next.set(Rating.Again, item_again);
    this.next.set(Rating.Hard, item_hard);
    this.next.set(Rating.Good, item_good);
    this.next.set(Rating.Easy, item_easy);
    return this.next.get(grade);
  }
  /**
  * Review next_ds
  */
  next_ds(t, g, retrievability) {
    const next_state = this.model.step({
      memoryState: this.current,
      elapsedDays: t,
      rating: g,
      retrievability
    });
    const card = TypeConvert.card(this.current);
    card.difficulty = next_state.difficulty;
    card.stability = next_state.stability;
    return card;
  }
  /**
  * Review next_interval
  */
  next_interval(next_hard, next_good, next_easy, interval) {
    const { maximum_interval } = this.parameters;
    const [hard_interval, good_interval, easy_interval] = calculateScheduleDays([
      this.scheduler_next_interval(next_hard, interval),
      this.scheduler_next_interval(next_good, interval),
      this.scheduler_next_interval(next_easy, interval)
    ], maximum_interval);
    next_hard.scheduled_days = hard_interval;
    next_hard.due = date_scheduler(this.review_time, hard_interval, true);
    next_good.scheduled_days = good_interval;
    next_good.due = date_scheduler(this.review_time, good_interval, true);
    next_easy.scheduled_days = easy_interval;
    next_easy.due = date_scheduler(this.review_time, easy_interval, true);
  }
  scheduler_next_interval(card, elapsed_days) {
    const params = this.parameters;
    const base = this.model.nextInterval(card, params.request_retention);
    return withFuzzing(base, elapsed_days, {
      enableFuzz: params.enable_fuzz,
      maximumInterval: params.maximum_interval
    }, this._seed);
  }
  /**
  * Review next_state
  */
  next_state(next_hard, next_good, next_easy) {
    next_hard.state = State.Review;
    next_hard.learning_steps = 0;
    next_good.state = State.Review;
    next_good.learning_steps = 0;
    next_easy.state = State.Review;
    next_easy.learning_steps = 0;
  }
};
var LongTermScheduler = class extends AbstractScheduler {
  newState(grade) {
    const exist = this.next.get(grade);
    if (exist) return exist;
    this.current.scheduled_days = 0;
    const first_interval = 0;
    const next_again = this.next_ds(first_interval, Rating.Again);
    const next_hard = this.next_ds(first_interval, Rating.Hard);
    const next_good = this.next_ds(first_interval, Rating.Good);
    const next_easy = this.next_ds(first_interval, Rating.Easy);
    this.next_interval(next_again, next_hard, next_good, next_easy, first_interval);
    this.next_state(next_again, next_hard, next_good, next_easy);
    this.update_next(next_again, next_hard, next_good, next_easy);
    return this.next.get(grade);
  }
  next_ds(t, g) {
    const next_state = this.model.step({
      memoryState: {
        difficulty: this.current.difficulty,
        stability: this.current.stability
      },
      elapsedDays: t,
      rating: g
    });
    const card = TypeConvert.card(this.current);
    card.difficulty = next_state.difficulty;
    card.stability = next_state.stability;
    return card;
  }
  /**
  * @see https://github.com/open-spaced-repetition/ts-fsrs/issues/98#issuecomment-2241923194
  */
  learningState(grade) {
    return this.reviewState(grade);
  }
  reviewState(grade) {
    const exist = this.next.get(grade);
    if (exist) return exist;
    const interval = this.elapsed_days;
    const next_again = this.next_ds(interval, Rating.Again);
    const next_hard = this.next_ds(interval, Rating.Hard);
    const next_good = this.next_ds(interval, Rating.Good);
    const next_easy = this.next_ds(interval, Rating.Easy);
    this.next_interval(next_again, next_hard, next_good, next_easy, interval);
    this.next_state(next_again, next_hard, next_good, next_easy);
    next_again.lapses += 1;
    this.update_next(next_again, next_hard, next_good, next_easy);
    return this.next.get(grade);
  }
  /**
  * Review/New next_interval
  */
  next_interval(next_again, next_hard, next_good, next_easy, interval) {
    const { maximum_interval } = this.parameters;
    const [again_interval, hard_interval, good_interval, easy_interval] = calculateScheduleDays([
      this.scheduler_next_interval(next_again, interval),
      this.scheduler_next_interval(next_hard, interval),
      this.scheduler_next_interval(next_good, interval),
      this.scheduler_next_interval(next_easy, interval)
    ], maximum_interval);
    next_again.scheduled_days = again_interval;
    next_again.due = date_scheduler(this.review_time, again_interval, true);
    next_hard.scheduled_days = hard_interval;
    next_hard.due = date_scheduler(this.review_time, hard_interval, true);
    next_good.scheduled_days = good_interval;
    next_good.due = date_scheduler(this.review_time, good_interval, true);
    next_easy.scheduled_days = easy_interval;
    next_easy.due = date_scheduler(this.review_time, easy_interval, true);
  }
  scheduler_next_interval(card, elapsed_days) {
    const params = this.parameters;
    const base = this.model.nextInterval({
      stability: card.stability,
      difficulty: card.difficulty
    }, params.request_retention);
    return withFuzzing(base, elapsed_days, {
      enableFuzz: params.enable_fuzz,
      maximumInterval: params.maximum_interval
    }, this._seed);
  }
  /**
  * Review/New next_state
  */
  next_state(next_again, next_hard, next_good, next_easy) {
    next_again.state = State.Review;
    next_again.learning_steps = 0;
    next_hard.state = State.Review;
    next_hard.learning_steps = 0;
    next_good.state = State.Review;
    next_good.learning_steps = 0;
    next_easy.state = State.Review;
    next_easy.learning_steps = 0;
  }
  update_next(next_again, next_hard, next_good, next_easy) {
    const item_again = {
      card: next_again,
      log: this.buildLog(Rating.Again)
    };
    const item_hard = {
      card: next_hard,
      log: super.buildLog(Rating.Hard)
    };
    const item_good = {
      card: next_good,
      log: super.buildLog(Rating.Good)
    };
    const item_easy = {
      card: next_easy,
      log: super.buildLog(Rating.Easy)
    };
    this.next.set(Rating.Again, item_again);
    this.next.set(Rating.Hard, item_hard);
    this.next.set(Rating.Good, item_good);
    this.next.set(Rating.Easy, item_easy);
  }
};
var Reschedule = class {
  fsrs;
  /**
  * Creates an instance of the `Reschedule` class.
  * @param fsrs - An instance of the FSRS class used for scheduling.
  */
  constructor(fsrs2) {
    this.fsrs = fsrs2;
  }
  /**
  * Replays a review for a card and determines the next review date based on the given rating.
  * @param card - The card being reviewed.
  * @param reviewed - The date the card was reviewed.
  * @param rating - The grade given to the card during the review.
  * @returns A `RecordLogItem` containing the updated card and review log.
  */
  replay(card, reviewed, rating) {
    return this.fsrs.next(card, reviewed, rating);
  }
  /**
  * Processes a manual review for a card, allowing for custom state, stability, difficulty, and due date.
  * @param card - The card being reviewed.
  * @param state - The state of the card after the review.
  * @param reviewed - The date the card was reviewed.
  * @param stability - (Optional) The stability of the card.
  * @param difficulty - (Optional) The difficulty of the card.
  * @param due - (Optional) The due date for the next review.
  * @returns A `RecordLogItem` containing the updated card and review log.
  * @throws Will throw an error if the state or due date is not provided when required.
  */
  handleManualRating(card, state, reviewed, stability, difficulty, due) {
    if (typeof state === "undefined") throw new FSRSValidationError("reschedule: state is required for manual rating");
    let log;
    let next_card;
    if (state === State.New) {
      log = {
        rating: Rating.Manual,
        state,
        due: due ?? reviewed,
        stability: card.stability,
        difficulty: card.difficulty,
        scheduled_days: card.scheduled_days,
        learning_steps: card.learning_steps,
        review: reviewed
      };
      next_card = createEmptyCard(reviewed);
      next_card.last_review = reviewed;
    } else {
      if (typeof due === "undefined") throw new FSRSValidationError("reschedule: due is required for manual rating");
      const scheduled_days = date_diff(due, reviewed, "days");
      log = {
        rating: Rating.Manual,
        state: card.state,
        due: card.last_review || card.due,
        stability: card.stability,
        difficulty: card.difficulty,
        scheduled_days: card.scheduled_days,
        learning_steps: card.learning_steps,
        review: reviewed
      };
      next_card = {
        ...card,
        state,
        due,
        last_review: reviewed,
        stability: stability || card.stability,
        difficulty: difficulty || card.difficulty,
        scheduled_days,
        reps: card.reps + 1
      };
    }
    return {
      card: next_card,
      log
    };
  }
  /**
  * Reschedules a card based on its review history.
  *
  * @param current_card - The card to be rescheduled.
  * @param reviews - An array of review history objects.
  * @returns An array of record log items representing the rescheduling process.
  */
  reschedule(current_card, reviews) {
    const collections = [];
    let cur_card = createEmptyCard(current_card.due);
    for (const review of reviews) {
      let item;
      review.review = TypeConvert.time(review.review);
      if (review.rating === Rating.Manual) item = this.handleManualRating(cur_card, review.state, review.review, review.stability, review.difficulty, review.due ? TypeConvert.time(review.due) : void 0);
      else item = this.replay(cur_card, review.review, review.rating);
      collections.push(item);
      cur_card = item.card;
    }
    return collections;
  }
  calculateManualRecord(current_card, now4, record_log_item, update_memory) {
    if (!record_log_item) return null;
    const { card: reschedule_card } = record_log_item;
    const cur_card = TypeConvert.card(current_card);
    if (cur_card.due.getTime() === reschedule_card.due.getTime()) return null;
    cur_card.scheduled_days = date_diff(reschedule_card.due, cur_card.due, "days");
    return this.handleManualRating(cur_card, reschedule_card.state, TypeConvert.time(now4), update_memory ? reschedule_card.stability : void 0, update_memory ? reschedule_card.difficulty : void 0, reschedule_card.due);
  }
};
var FSRS = class {
  strategyHandler = /* @__PURE__ */ new Map();
  Scheduler;
  #parameters;
  #model;
  /** @deprecated Use DefaultScheduler(options) or defineScheduler(...).create({ config }). */
  constructor(parameters = {}) {
    this.parameters = parameters;
  }
  /** @deprecated Use the model property of a scheduler created with DefaultScheduler or defineScheduler. */
  get model() {
    return this.#model;
  }
  /** @deprecated Use scheduler.config on a scheduler created with DefaultScheduler or defineScheduler. */
  get parameters() {
    return this.#parameters;
  }
  /** @deprecated Create a new scheduler with the updated config; scheduler.config is readonly. */
  set parameters(parameters) {
    const normalized = this.prepare_parameters(parameters);
    this.#parameters = new Proxy(normalized, this.params_handler_proxy());
    this.rebuildModel();
    this.Scheduler = normalized.enable_short_term ? BasicScheduler : LongTermScheduler;
  }
  prepare_parameters = (parameters) => {
    const generated = generatorParameters(parameters);
    generated.w = clipFSRS6Parameters(Array.from(generated.w), generated.relearning_steps.length, generated.enable_short_term);
    return generated;
  };
  rebuildModel() {
    this.#model = FSRS6Model.create({
      config: {
        weights: this.#parameters.w,
        enableShortTerm: this.#parameters.enable_short_term,
        numRelearningSteps: this.#parameters.relearning_steps.length
      },
      bypass: true
    });
  }
  params_handler_proxy() {
    const _this = this;
    return { set: (target, prop, value) => {
      if (prop === "enable_short_term") _this.Scheduler = value === true ? BasicScheduler : LongTermScheduler;
      else if (prop === "w") value = clipFSRS6Parameters(migrateFSRS6Parameters(value), target.relearning_steps.length, target.enable_short_term);
      Reflect.set(target, prop, value);
      if (prop === "enable_short_term" || prop === "w") _this.rebuildModel();
      return true;
    } };
  }
  /** @deprecated Compose policies with defineScheduler(...).use(defineMiddleware(...)). */
  useStrategy(mode, handler) {
    this.strategyHandler.set(mode, handler);
    return this;
  }
  /** @deprecated Create a new scheduler definition with only the required middleware. */
  clearStrategy(mode) {
    if (mode) this.strategyHandler.delete(mode);
    else this.strategyHandler.clear();
    return this;
  }
  getScheduler(card, now4) {
    return new (this.strategyHandler.get("Scheduler") || this.Scheduler)(card, now4, this.#model, this.#parameters, this.strategyHandler);
  }
  /**
  * Display the collection of cards and logs for the four scenarios after scheduling the card at the current time.
  * @param card Card to be processed
  * @param now Current time or scheduled time
  * @example
  * ```typescript
  * const card: Card = createEmptyCard(new Date());
  * const f = fsrs();
  * const recordLog = f.repeat(card, new Date());
  * ```
  * @deprecated Use scheduler.preview({ card, now }) with the new card shape.
  */
  repeat(card, now4) {
    return this.getScheduler(card, now4).preview();
  }
  /**
  * Display the collection of cards and logs for the card scheduled at the current time, after applying a specific grade rating.
  * @param card Card to be processed
  * @param now Current time or scheduled time
  * @param grade Rating of the review (Again, Hard, Good, Easy)
  * @example
  * ```typescript
  * const card: Card = createEmptyCard(new Date());
  * const f = fsrs();
  * const recordLogItem = f.next(card, new Date(), Rating.Again);
  * ```
  * @deprecated Use scheduler.review({ card, now, grade }) with the new card shape.
  */
  next(card, now4, grade) {
    const instance = this.getScheduler(card, now4);
    const g = TypeConvert.rating(grade);
    if (g === Rating.Manual) throw new FSRSValidationError("Cannot review a manual rating");
    return instance.review(g);
  }
  /**
  * Get the retrievability of the card
  * @param card  Card to be processed
  * @param now  Current time or scheduled time
  * @returns  The retrievability of the card
  * @deprecated Use scheduler.model.forgettingCurve(memoryState, elapsedDays). Return 0 for New cards and clamp elapsedDays to at least zero; preserve floored elapsed 24-hour days for legacy parity rather than assuming calendar-day chronology is equivalent.
  */
  retrievability(card, now4) {
    const processedCard = TypeConvert.card(card);
    now4 = now4 ? TypeConvert.time(now4) : /* @__PURE__ */ new Date();
    const t = processedCard.state !== State.New ? Math.max(date_diff(now4, processedCard.last_review, "days"), 0) : 0;
    return processedCard.state !== State.New ? this.#model.forgettingCurve(processedCard, t) : 0;
  }
  /**
  *
  * @param card Card to be processed
  * @param log last review log
  * @example
  * ```typescript
  * const now = new Date();
  * const f = fsrs();
  * const emptyCard = createEmptyCard(now);
  * const repeat = f.repeat(emptyCard, now);
  * const { card, log } = repeat[Rating.Hard];
  * const rollbackCard = f.rollback(card, log);
  * ```
  * @deprecated Use scheduler.rollback({ card, revlog }) with matching new-format records.
  */
  rollback(card, log) {
    const processedCard = TypeConvert.card(card);
    const processedLog = TypeConvert.review_log(log);
    if (processedLog.rating === Rating.Manual) throw new FSRSValidationError("Cannot rollback a manual rating");
    let last_due;
    let last_review;
    let last_lapses;
    switch (processedLog.state) {
      case State.New:
        last_due = processedLog.due;
        last_review = void 0;
        last_lapses = 0;
        break;
      case State.Learning:
      case State.Relearning:
      case State.Review:
        last_due = processedLog.review;
        last_review = processedLog.due;
        last_lapses = processedCard.lapses - (processedLog.rating === Rating.Again && processedLog.state === State.Review ? 1 : 0);
    }
    return {
      ...processedCard,
      due: last_due,
      stability: processedLog.stability,
      difficulty: processedLog.difficulty,
      scheduled_days: processedLog.scheduled_days,
      reps: Math.max(0, processedCard.reps - 1),
      lapses: Math.max(0, last_lapses),
      learning_steps: processedLog.learning_steps,
      state: processedLog.state,
      last_review
    };
  }
  /**
  *
  * @param card Card to be processed
  * @param now Current time or scheduled time
  * @param reset_count Should the review count information(reps,lapses) be reset. (Optional)
  * @example
  * ```typescript
  * const now = new Date();
  * const f = fsrs();
  * const emptyCard = createEmptyCard(now);
  * const scheduling_cards = f.repeat(emptyCard, now);
  * const { card, log } = scheduling_cards[Rating.Hard];
  * const forgetCard = f.forget(card, new Date(), true);
  * ```
  * @deprecated Use scheduler.forget({ card, now }); configure clearStatsOnForget explicitly to preserve the desired counter behavior.
  */
  forget(card, now4, reset_count = false) {
    const processedCard = TypeConvert.card(card);
    now4 = TypeConvert.time(now4);
    const scheduled_days = processedCard.state === State.New ? 0 : date_diff(now4, processedCard.due, "days");
    const forget_log = {
      rating: Rating.Manual,
      state: processedCard.state,
      due: processedCard.due,
      stability: processedCard.stability,
      difficulty: processedCard.difficulty,
      scheduled_days,
      learning_steps: processedCard.learning_steps,
      review: now4
    };
    return {
      card: {
        ...processedCard,
        due: now4,
        stability: 0,
        difficulty: 0,
        scheduled_days: 0,
        reps: reset_count ? 0 : processedCard.reps,
        lapses: reset_count ? 0 : processedCard.lapses,
        learning_steps: 0,
        state: State.New,
        last_review: processedCard.last_review
      },
      log: forget_log
    };
  }
  /**
  * Reschedules the current card and returns the rescheduled collections and reschedule item.
  *
  * @param {CardInput | Card} current_card - The current card to be rescheduled.
  * @param {Array<FSRSHistory>} reviews - The array of FSRSHistory objects representing the reviews.
  * @param {Partial<RescheduleOptions>} options - The optional reschedule options.
  * @returns {IReschedule} - The rescheduled collections and reschedule item.
  *
  * @example
  * ```typescript
  * const f = fsrs()
  * const grades: Grade[] = [Rating.Good, Rating.Good, Rating.Good, Rating.Good]
  * const reviews_at = [
  *   new Date(2024, 8, 13),
  *   new Date(2024, 8, 13),
  *   new Date(2024, 8, 17),
  *   new Date(2024, 8, 28),
  * ]
  *
  * const reviews: FSRSHistory[] = []
  * for (let i = 0; i < grades.length; i++) {
  *   reviews.push({
  *     rating: grades[i],
  *     review: reviews_at[i],
  *   })
  * }
  *
  * const results_short = scheduler.reschedule(
  *   createEmptyCard(),
  *   reviews,
  *   {
  *     skipManual: false,
  *   }
  * )
  * console.log(results_short)
  * ```
  * @deprecated Use Reschedule from ts-fsrs/reschedule; convert history to rating/reviewTime records.
  */
  reschedule(current_card, reviews = [], options = {}) {
    const { reviewsOrderBy, skipManual = true, now: now4 = /* @__PURE__ */ new Date(), update_memory_state: updateMemoryState = false } = options;
    if (reviewsOrderBy && typeof reviewsOrderBy === "function") reviews.sort(reviewsOrderBy);
    if (skipManual) reviews = reviews.filter((review) => review.rating !== Rating.Manual);
    const rescheduleSvc = new Reschedule(this);
    const collections = rescheduleSvc.reschedule(options.first_card || createEmptyCard(), reviews);
    const len = collections.length;
    const cur_card = TypeConvert.card(current_card);
    return {
      collections,
      reschedule_item: rescheduleSvc.calculateManualRecord(cur_card, now4, len ? collections[len - 1] : void 0, updateMemoryState) ?? null
    };
  }
};
var fsrs = (params) => {
  return new FSRS(params || {});
};
var defaultSchedulerMiddlewares = [
  schedulerDesiredRetentionMiddleware,
  schedulerFuzzingMiddleware,
  schedulerStatsMiddleware,
  schedulerScheduledDaysMiddleware,
  schedulerLearningStepsMiddleware,
  schedulerMaximumIntervalMiddleware,
  schedulerMonotonicIntervalMiddleware
];
function createRuntimeDefaultSchedulerDefinition(model) {
  return defineScheduler({
    model,
    chrono: dateChrono
  }).use(...defaultSchedulerMiddlewares);
}
var schedulerPresetLoaders = {
  "FSRS-3": async () => {
    const { FSRS3Model: FSRS3Model2, migrateFSRS3Parameters: migrateFSRS3Parameters2 } = await Promise.resolve().then(() => (init_fsrs_3(), fsrs_3_exports));
    return {
      model: FSRS3Model2,
      migrateParameters: migrateFSRS3Parameters2
    };
  },
  "FSRS-4": async () => {
    const { FSRS4Model: FSRS4Model2, migrateFSRS4Parameters: migrateFSRS4Parameters2 } = await Promise.resolve().then(() => (init_fsrs_4(), fsrs_4_exports));
    return {
      model: FSRS4Model2,
      migrateParameters: migrateFSRS4Parameters2
    };
  },
  "FSRS-4.5": async () => {
    const { FSRS4Dot5Model: FSRS4Dot5Model2, migrateFSRS4Dot5Parameters: migrateFSRS4Dot5Parameters2 } = await Promise.resolve().then(() => (init_fsrs_4dot5(), fsrs_4dot5_exports));
    return {
      model: FSRS4Dot5Model2,
      migrateParameters: migrateFSRS4Dot5Parameters2
    };
  },
  "FSRS-5": async () => {
    const { FSRS5Model: FSRS5Model2, migrateFSRS5Parameters: migrateFSRS5Parameters2 } = await Promise.resolve().then(() => (init_fsrs_5(), fsrs_5_exports));
    return {
      model: FSRS5Model2,
      migrateParameters: migrateFSRS5Parameters2
    };
  },
  "FSRS-6": async () => {
    const { FSRS6Model: FSRS6Model2, migrateFSRS6Parameters: migrateFSRS6Parameters2 } = await Promise.resolve().then(() => (init_fsrs_6(), fsrs_6_exports));
    return {
      model: FSRS6Model2,
      migrateParameters: migrateFSRS6Parameters2
    };
  },
  "FSRS-7": async () => {
    const { FSRS7Model: FSRS7Model2, migrateFSRS7Parameters: migrateFSRS7Parameters2 } = await Promise.resolve().then(() => (init_fsrs_7(), fsrs_7_exports));
    return {
      model: FSRS7Model2,
      migrateParameters: migrateFSRS7Parameters2
    };
  }
};
var schedulerPresetCache = /* @__PURE__ */ new Map();
async function getSchedulerPreset(version2) {
  const resolvedVersion = version2 ?? "FSRS-7";
  if (!Object.hasOwn(schedulerPresetLoaders, resolvedVersion)) throw new FSRSValidationError(`Unsupported FSRS version "${version2}"`);
  let preset = schedulerPresetCache.get(resolvedVersion);
  if (!preset) {
    preset = schedulerPresetLoaders[resolvedVersion]().then(({ model, migrateParameters }) => ({
      definition: createRuntimeDefaultSchedulerDefinition(model),
      migrateParameters
    }));
    schedulerPresetCache.set(resolvedVersion, preset);
  }
  return preset;
}
async function DefaultScheduler(options = {}) {
  const version2 = options.version ?? "FSRS-7";
  const isFSRS7 = version2 === "FSRS-7";
  const preset = await getSchedulerPreset(version2);
  const { weights, enableShortTerm = true, desiredRetention = 0.9, learningSteps = defaultLearningSteps, relearningSteps = defaultRelearningSteps, allowModelOverride = isFSRS7, enableFuzz = false, maximumInterval = DEFAULT_MAXIMUM_INTERVAL } = options;
  const migratedWeights = preset.migrateParameters(weights ? Array.from(weights) : void 0, relearningSteps.length, enableShortTerm);
  return preset.definition.create({ config: {
    fractionalDays: isFSRS7,
    weights: migratedWeights,
    enableShortTerm,
    numRelearningSteps: relearningSteps.length,
    desiredRetention,
    learningSteps: Array.from(learningSteps),
    relearningSteps: Array.from(relearningSteps),
    graduatingInterval: options.graduatingInterval,
    allowModelOverride,
    enableFuzz,
    maximumInterval,
    clearStatsOnForget: options.clearStatsOnForget
  } });
}
export {
  AbstractScheduler,
  CLAMP_PARAMETERS,
  COST_ADR_DEFAULT_GOAL_COST_WEIGHT,
  COST_ADR_DEFAULT_POLICY,
  ConvertStepUnitToMinutes,
  DEFAULT_LEECH_THRESHOLD,
  DEFAULT_MAXIMUM_INTERVAL,
  DefaultScheduler,
  FSRS,
  FSRS5_DECAY as FSRS5_DEFAULT_DECAY,
  FSRS6_DECAY as FSRS6_DEFAULT_DECAY,
  FSRSMemoryStateSchema,
  FSRSVersion,
  FUZZ_RANGES,
  Grades,
  INIT_S_MAX,
  Rating,
  S_MAX,
  S_MIN,
  State,
  StrategyMode,
  TypeConvert,
  W17_W18_Ceiling,
  calculateLearningSteps,
  calculateScheduleDay,
  calculateScheduleDays,
  checkParameters,
  clamp,
  costAdrConfigSchema,
  costAdrPolicySchema,
  createEmptyCard,
  createSchedulerFuzzingMiddleware,
  dateChrono,
  dateDiffInDays2 as dateDiffInDays,
  date_diff,
  date_scheduler,
  defaultGraduatingInterval,
  defaultLearningSteps,
  defaultRelearningSteps,
  default_enable_fuzz,
  default_enable_short_term,
  default_maximum_interval,
  default_request_retention,
  default_w,
  defineChrono,
  defineMiddleware,
  defineModel,
  defineScheduler,
  desiredRetentionConfigSchema,
  desiredRetentionSchema,
  elapsedDaysSchema,
  fnv1aMulberry32Rng,
  formatDate,
  fsrs,
  fuzzingCardFieldsSchema,
  fuzzingCardInitInputSchema,
  fuzzingConfigSchema,
  fuzzingRevlogFieldsSchema,
  generatorParameters,
  getFuzzRange,
  get_fuzz_range,
  gradeSchema,
  learningStepFieldsSchema,
  learningStepsConfigSchema,
  leechCardFieldsSchema,
  leechConfigSchema,
  monotonicIntervalConfigSchema,
  numericChrono,
  ratingSchema,
  roundTo,
  scheduledDaysFieldsSchema,
  scheduledDaysSchema,
  schedulerCostAdrMiddleware,
  schedulerDesiredRetentionMiddleware,
  schedulerFuzzingMiddleware,
  schedulerLearningStepsMiddleware,
  schedulerLeechMiddleware,
  schedulerMaximumIntervalMiddleware,
  schedulerMonotonicIntervalMiddleware,
  schedulerScheduledDaysMiddleware,
  schedulerStatsMiddleware,
  show_diff_message,
  stateSchema,
  statsConfigSchema,
  statsFieldsSchema,
  temporalInstantChrono,
  withFuzzing
};
