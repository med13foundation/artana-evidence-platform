/** @type {import("stylelint").Config} */
module.exports = {
  extends: ["stylelint-config-standard", "stylelint-config-tailwindcss"],
  plugins: ["stylelint-order"],
  rules: {
    "alpha-value-notation": "number",
    "color-function-notation": null,
    "color-function-alias-notation": null,
    "hue-degree-notation": "number",
    "comment-empty-line-before": null,
    "custom-property-empty-line-before": null,
    "declaration-block-no-duplicate-custom-properties": null,
    "selector-class-pattern": [
      "^[a-z0-9\\-_/]+$",
      {
        message:
          "Class names should remain lowercase kebab-case or Tailwind-style tokens.",
      },
    ],
  },
};
