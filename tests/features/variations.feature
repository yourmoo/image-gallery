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

  @F3_1 @stage7
  Scenario: Images are shown at the default size when I ask for nothing
    When I open the gallery
    Then the images are rendered at size "medium"
    And the images have no filters applied

  @F3_1 @F3_2 @stage7
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
  # a configured ceiling and floor. The named sizes are a select; a custom size
  # is a field beside it, because WxH cannot be enumerated.
  @F3_2 @stage7
  Scenario Outline: Asking for a custom size
    When I open the gallery with size "<size>"
    Then the response status is 200
    And the images are rendered at <width> by <height> pixels

    Examples:
      | size     | width | height |
      | 300x300  | 300   | 300    |
      | 1200x900 | 1200  | 900    |

  @F3_6 @stage8
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

  @F2_3 @F3_2 @stage8
  Scenario: A custom size is kept when I move between pages
    When I open the gallery with size "640x480"
    And I open page 2 of the gallery
    Then the images are rendered at 640 by 480 pixels
    And the page shows images 11 to 20

  @F3_2 @stage12
  Scenario: The gallery offers a control for a custom size
    When I open the gallery
    Then the page offers a field for a custom size

  @F3_2 @stage12
  Scenario: Entering a custom size in the gallery
    When I open the gallery
    And I enter the custom size "640x480"
    Then the images are rendered at 640 by 480 pixels

  @F3_6 @stage12
  Scenario: A custom size entered out of bounds is rejected like any other
    When I open the gallery
    And I enter the custom size "6000x6000"
    Then the images are rendered at size "medium"
    And the page explains that "6000x6000" is not a valid size

  @F3_3 @stage7
  Scenario: Viewing the collection in grayscale
    When I turn grayscale on
    Then the response status is 200
    And the images are rendered in grayscale

  @F3_4 @stage7
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
  @F3_5 @stage7
  Scenario: Combining grayscale and blur
    When I turn grayscale on
    And I set the blur to 7
    Then the response status is 200
    And the images are rendered in grayscale
    And the images are rendered with blur 7

  @F3_5 @stage7
  Scenario: Size and filters apply together
    When I choose the "large" size
    And I turn grayscale on
    And I set the blur to 3
    Then the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 3

  # F3.6 — rejected at the validation boundary, recovered in the page.
  @F3_6 @stage8
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

  @F3_6 @stage8
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

  @F3_6 @stage8
  Scenario: An invalid count falls back to the default and says so
    When I open the gallery with a count of "75"
    Then the response status is 200
    And the page shows 10 images in a grid
    And the page explains that "75" is not a valid image count

  # One bad parameter must not discard the good ones alongside it.
  @F3_6 @stage8
  Scenario: A valid filter survives an invalid one
    When I open the gallery with size "enormous" and blur 6
    Then the images are rendered at size "medium"
    And the images are rendered with blur 6
    And the page explains that "enormous" is not a valid size

  @F2_3 @stage8
  Scenario: Active variations are kept when I move between pages
    Given I am viewing large grayscale images with blur 4
    When I open page 2 of the gallery
    Then the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 4
    And the page shows images 11 to 20
