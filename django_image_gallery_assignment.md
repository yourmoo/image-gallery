# Take-Home Assignment: Django Image Gallery Application

## Overview

Build a Django web application that integrates with the public image service at https://picsum.dev/.

The application should dynamically generate and render image URLs through backend logic and support configurable image behaviors.

This exercise focuses on:

- clean architecture
- resilient API integration
- performance and caching strategy
- testability and maintainability
- containerized delivery

The assignment should remain lightweight to run locally. Do not add new external services.

Feel free to use any AI tools of your choice to complete the assignment.

However, you will be expected to have a complete understanding of your code, 
and be able to rationalize and justify your architectural desicions and design choices.

Important API constraint:
- The PicSUM:DEV API does not provide a list endpoint for image metadata.
- The gallery must therefore be built by issuing multiple direct image requests per page.

---

## Objective

Build a configurable image gallery application with multiple image transformations, predictable image behavior options, and resilient handling of upstream failures.

The application must be fully containerized and runnable with minimal setup.

---

## Core Requirements

### Image Gallery

- Display a collection of images in a grid layout.
- The number of images displayed must be configurable.
- Images must be generated dynamically through backend logic.
- Images should vary based on parameters such as size and visual filters.
- Add pagination as a required feature.
  - Page state must be URL-driven (for example, query params).
  - Invalid page values must redirect to page 1 and display a user-facing validation message.
  - Pagination links must preserve active filters and sizing parameters.
  - The gallery should show 10 images per page by default, with the image count being configurable by the user via UI
  - Page 1 must fetch images 1-10, page 2 must fetch images 11-20, and so on.
  - Because no list endpoint exists, each page must be composed by multiple upstream image calls.

### Image Variations

The application must support different image variations, including:

- Multiple named sizes (for example: small, medium, large).
- Normal (default) images.
- Grayscale rendering.
- Blur effects with multiple intensity levels (0-10).

#### Combination Support
- Allow grayscale and blur to be used together.
- Reject invalid transformation values with a clear validation error.

### Image Detail View

- Implement a detail view for individual images.
- The detail page must:
  - display a larger version of the image
  - reflect all active transformations
  - show the parameters used to generate the image

### Backend-Driven URL Generation

- All image generation logic must be implemented on the backend.
- Templates must not construct image URLs directly.
- Centralize URL generation in a service-layer component.
- Use Django URL reversing for internal route links.
- Downloaded upstream images must be cached while the app is running.

---

## Architecture Requirements

### Service Layer and Boundaries

- Implement a clear abstraction layer for interacting with picsum.dev.
- API-specific logic must not live in views or templates.
- The design should allow replacing the image provider with minimal changes.
- Provide a clear module structure (for example: service, transformations, validation, views).

### Configuration

Make key parameters configurable via environment-driven settings where appropriate, including:

- default image size
- default image count per page
- cache settings (such as TTL)
- retry/timeout behavior

---

## Resilience and Error Handling Requirements

### Upstream Resilience

- Implement timeout handling for external API calls.
- Implement retry behavior with backoff for transient failures.
- Implement fallback behavior using cached data when upstream calls fail.


### Error Handling Matrix

Handle these cases explicitly and consistently:

- invalid/unsupported parameters
- upstream timeout
- upstream non-success response
- missing data and empty gallery results
- no cached fallback available

For each case, ensure:

- clear user-facing behavior (not raw exception output)
- predictable HTTP status behavior
- useful logs for debugging

---

## Performance Requirements

### Caching

- Implement caching for generated image metadata or URL payloads.
- Cache key strategy must include all relevant output-affecting inputs, such as:
  - image parameters
  - transformations
  - relevant config values
- Prevent duplicate upstream calls for repeated equivalent requests.

### Efficiency and Repeatability

- Avoid unnecessary recomputation of identical outputs.
- Document and justify your cache policy and invalidation behavior.
- Demonstrate repeat-request performance improvements.
- Include a lightweight concurrency validation approach (for example, repeated concurrent gallery requests) and describe observed cache behavior.

---

## Security and Validation Requirements

- Validate and sanitize all user-provided query parameters.
- Use allow-lists for constrained parameters (size, transform options, blur ranges, page).
---

## User Interface Requirements

- Provide a simple, clear, and functional UI.
- Focus on usability over visual complexity.
- Ensure responsive behavior on common viewport sizes (mobile, tablet, desktop).
- Display a loading indicator while gallery images are downloading.

---

## Testing Requirements (Required)

Automated tests are required.

- Include unit tests for core business logic (service, transformations, validation).
- Include integration tests around API interaction boundaries (mocked/stubbed external dependency is acceptable).
- Maintain at least 70% automated test coverage.
- Document what is covered and what is intentionally out of scope.
---

## Logging and Observability Requirements

- Provide structured logs for:
  - upstream API requests/responses
  - cache hit/miss behavior
  - handled errors and fallback paths
- Logs must be available from container output.
- Include enough context in logs to diagnose failures.

---

## Containerization Requirements

The application must be runnable using container tooling.

### Required

- Dockerfile
- Docker Compose configuration

### Expected behavior

- The application starts with a single command.
- No manual setup steps should be required.
- Include a health endpoint suitable for container health checks.

---

## Documentation Requirements

Include a README with clear instructions and rationale.

### Build

- How to build the application
- Prerequisites

### Run

- How to start the application
- How to access it once running

### Test

- How to run tests
- Coverage command and reported result
- What is covered by tests

### API Contract

- Document application endpoints, accepted parameters, and response/error behavior.

### Design Decisions

- Key architectural decisions
- Trade-offs made
- Assumptions
- State model choice and rationale
- Resilience strategy and rationale

### Performance Notes

- Targets you defined
- How you measured them
- Observed outcomes and interpretation

### Future Improvements

- What you would improve or extend with more time

---

## Evaluation Criteria (Qualitative)

Submissions will be evaluated qualitatively based on:

- code structure, organization, and separation of concerns
- quality of service abstraction and provider boundary design
- correctness and clarity of parameter validation and URL generation
- resilience under upstream failure and quality of fallback behavior
- caching strategy quality and demonstrated performance reasoning
- testing depth, reliability, and coverage completeness
- observability quality (logs, diagnosability)
- containerized run experience and developer ergonomics
- clarity of documentation and design rationale
- overall completeness and consistency of implementation

---

## Submission Expectations

- Provide source code in a github repository.
- Ensure the application can be built and run using documented steps.
- Ensure all required sections above are addressed.
