import brandJson from "@core/brand.json";

export interface Brand {
  name: string;
  cli: string;
  distribution: string;
  env_prefix: string;
  tagline: string;
  demo_label: string;
  repository: string;
}

/** User-facing product identity. Edit src/issueradar/brand.json to rename (ADR 0002). */
export const brand: Brand = brandJson;
