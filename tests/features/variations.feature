Feature: Image variations
  As someone browsing the gallery
  I want to change how the images are rendered
  So that I can view the collection at the size and style I prefer

  Covers F3.1-F3.6. Invalid values fall back to their default and explain
  themselves rather than dead-ending the page — see docs/core-features.md
  for why that reading of "reject" was chosen.

  Background:
    Given the gallery is available
    And the collection holds 100 images

  Scenario: Images are shown at the default size when I ask for nothing
    When I open the gallery
    Then the images are rendered at size "medium"
    And the images have no filters applied

  Scenario Outline: Choosing a named size
    When I choose the "<size>" size
    Then the response status is 200
    And the images are rendered at size "<size>"

    Examples:
      | size   |
      | small  |
      | medium |
      | large  |

  # Custom dimensions are a fourth form of the same size parameter, bounded by
  # a configured ceiling and floor. The UI offers named sizes only.
  Scenario Outline: Asking for a custom size
    When I open the gallery with size "<size>"
    Then the response status is 200
    And the images are rendered at <width> by <height> pixels

    Examples:
      | size     | width | height |
      | 300x300  | 300   | 300    |
      | 1200x900 | 1200  | 900    |

  Scenario Outline: A custom size outside the allowed bounds is rejected
    When I open the gallery with size "<size>"
    Then the response status is 200
    And the images are rendered at size "medium"
    And the page explains that "<size>" is not a valid size

    Examples: Above the ceiling
      | size      |
      | 6000x6000 |
      | 1601x400  |

    Examples: Below the floor
      | size    |
      | 0x0     |
      | 8x8     |

    Examples: Malformed
      | size     |
      | 300x     |
      | 300x300x |
      | -100x100 |

  Scenario: A custom size is kept when I move between pages
    When I open the gallery with size "640x480"
    And I open page 2 of the gallery
    Then the images are rendered at 640 by 480 pixels
    And the page shows images 11 to 20

  Scenario: Viewing the collection in grayscale
    When I turn grayscale on
    Then the response status is 200
    And the images are rendered in grayscale

  Scenario Outline: Blurring the images
    When I set the blur to <blur>
    Then the response status is 200
    And the images are rendered with blur <blur>

    Examples: The ends and middle of the accepted range
      | blur |
      | 0    |
      | 5    |
      | 10   |

  # F3.5 — the two filters must be usable at once.
  Scenario: Combining grayscale and blur
    When I turn grayscale on
    And I set the blur to 7
    Then the response status is 200
    And the images are rendered in grayscale
    And the images are rendered with blur 7

  Scenario: Size and filters apply together
    When I choose the "large" size
    And I turn grayscale on
    And I set the blur to 3
    Then the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 3

  # F3.6 — rejected at the validation boundary, recovered in the page.
  Scenario Outline: An invalid size falls back to the default and says so
    When I open the gallery with size "<size>"
    Then the response status is 200
    And the images are rendered at size "medium"
    And the page explains that "<size>" is not a valid size

    Examples:
      | size    |
      | huge    |
      | tiny    |
      | 42      |
      | LARGE!! |

  Scenario Outline: A blur outside the range falls back to none and says so
    When I open the gallery with blur "<blur>"
    Then the response status is 200
    And the images have no blur applied
    And the page explains that "<blur>" is not a valid blur

    Examples: Outside 0-10
      | blur |
      | 11   |
      | -1   |
      | 99   |

    Examples: Not a whole number
      | blur |
      | high |
      | 3.5  |

  Scenario: An invalid count falls back to the default and says so
    When I open the gallery with a count of "75"
    Then the response status is 200
    And the page shows 10 images in a grid
    And the page explains that "75" is not a valid image count

  # One bad parameter must not discard the good ones alongside it.
  Scenario: A valid filter survives an invalid one
    When I open the gallery with size "enormous" and blur 6
    Then the images are rendered at size "medium"
    And the images are rendered with blur 6
    And the page explains that "enormous" is not a valid size

  Scenario: Active variations are kept when I move between pages
    Given I am viewing large grayscale images with blur 4
    When I open page 2 of the gallery
    Then the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 4
    And the page shows images 11 to 20
