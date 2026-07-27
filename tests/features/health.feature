Feature: Application health
  As an operator running the gallery in a container
  I want a health endpoint and a landing page
  So that orchestration can tell whether the app is serving

  Scenario: The health endpoint reports a healthy application
    Given the application is running
    When I request the health endpoint
    Then the response status is 200
    And the response reports status "ok"

  Scenario: The landing page renders
    Given the application is running
    When I request the landing page
    Then the response status is 200
    And the page shows the gallery heading
