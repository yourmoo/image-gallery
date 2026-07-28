Feature: Image detail view
  As someone browsing the gallery
  I want to open a single image on its own page
  So that I can see it larger and know how it was generated

  Covers F4.1-F4.4. The detail view always renders at "large" while
  carrying the active filters over — see docs/core-features.md for why
  size is treated as presentation rather than as a transformation.

  Background:
    Given the gallery is available
    And the collection holds 100 images

  Scenario: Opening an image from the gallery
    When I open the gallery
    And I select the third image
    Then the response status is 200
    And I am on the detail page for image 3

  Scenario: The detail view shows a larger image
    When I open the detail page for image 7
    Then the response status is 200
    And the image is rendered at size "large"

  # F4.2 vs F4.3 — "larger" wins for size even when the gallery was small.
  Scenario Outline: The detail view is large whatever size the gallery used
    Given I am viewing the gallery at the "<size>" size
    When I select the first image
    Then the image is rendered at size "large"

    Examples:
      | size   |
      | small  |
      | medium |
      | large  |

  # A custom size larger than the named "large" is kept, because dropping to
  # large would make the detail view smaller than the grid — the opposite of
  # what "display a larger version" asks for.
  Scenario: A custom size larger than large is kept on the detail page
    When I open the gallery with size "1200x900"
    And I select the first image
    Then the image is rendered at 1200 by 900 pixels

  Scenario: A custom size smaller than large is replaced by large
    When I open the gallery with size "300x300"
    And I select the first image
    Then the image is rendered at size "large"

  # F4.3 — the filters, unlike size, carry over.
  Scenario: Active filters carry over to the detail view
    Given I am viewing large grayscale images with blur 4
    When I select the first image
    Then the image is rendered in grayscale
    And the image is rendered with blur 4

  Scenario: An unfiltered gallery gives an unfiltered detail view
    When I open the gallery
    And I select the first image
    Then the image has no filters applied

  # F4.4 — the parameters panel must report what was actually used, which
  # includes the size the detail view chose rather than the one I browsed at.
  Scenario: The detail page lists the parameters used
    Given I am viewing the gallery at the "small" size
    And I have turned grayscale on
    And I have set the blur to 6
    When I select the second image
    Then the page shows the image identifier 2
    And the page shows the size "large"
    And the page shows that grayscale is on
    And the page shows the blur value 6

  Scenario: The parameters panel reports defaults when nothing is chosen
    When I open the detail page for image 5
    Then the page shows the image identifier 5
    And the page shows the size "large"
    And the page shows that grayscale is off
    And the page shows the blur value 0

  Scenario: Returning to the gallery keeps my place and my filters
    Given I am viewing large grayscale images with blur 4
    When I open page 3 of the gallery
    And I select the first image
    And I follow the link back to the gallery
    Then the page shows images 21 to 30
    And the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 4

  Scenario Outline: An image outside the collection is not found
    When I open the detail page for image "<id>"
    Then the response status is 404

    Examples: Beyond the catalogue
      | id  |
      | 101 |
      | 999 |

    Examples: Not a valid identifier
      | id  |
      | 0   |
      | -3  |

  Scenario: An invalid filter on the detail page falls back and says so
    When I open the detail page for image 4 with blur "99"
    Then the response status is 200
    And the image has no blur applied
    And the page explains that "99" is not a valid blur
