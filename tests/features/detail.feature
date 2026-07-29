Feature: Image detail view
  As someone browsing the gallery
  I want to open a single image on its own page
  So that I can see it larger and know how it was generated

  Covers F4.1-F4.4. The detail view *opens* at "large" while carrying the
  active filters over — see docs/core-features.md for why size is treated as
  presentation rather than as a transformation.

  Size, grayscale, and blur are then adjustable on the page. The default is
  what docs/adr/0007-detail-view-size.md decided and the control is what its
  2026-07-29 amendment added, so the scenarios below distinguish carefully
  between what the page does on arrival and what it does when asked.

  Background:
    Given the gallery is available
    And the collection holds 100 images

  @F4_1 @stage9
  Scenario: Opening an image from the gallery
    When I open the gallery
    And I select the third image
    Then the response status is 200
    And I am on the detail page for image 3

  @F4_2 @stage9
  Scenario: The detail view shows a larger image
    When I open the detail page for image 7
    Then the response status is 200
    And the image is rendered at size "large"

  # F4.2 vs F4.3 — "larger" wins for size even when the gallery was small.
  @F4_2 @stage9
  Scenario Outline: The detail view opens large whatever size the gallery used
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
  @F4_2 @stage9
  Scenario: A custom size larger than large is kept when the page opens
    When I open the gallery with size "1200x900"
    And I select the first image
    Then the image is rendered at 1200 by 900 pixels

  @F4_2 @stage9
  Scenario: A custom size smaller than large is replaced by large on arrival
    When I open the gallery with size "300x300"
    And I select the first image
    Then the image is rendered at size "large"

  # F4.3 — the filters, unlike size, carry over.
  @F4_3 @stage10
  Scenario: Active filters carry over to the detail view
    Given I am viewing large grayscale images with blur 4
    When I select the first image
    Then the image is rendered in grayscale
    And the image is rendered with blur 4

  @F4_3 @stage10
  Scenario: An unfiltered gallery gives an unfiltered detail view
    When I open the gallery
    And I select the first image
    Then the image has no filters applied

  # F4.4 — the parameters panel must report what was actually used, which
  # includes the size the detail view chose rather than the one I browsed at.
  @F4_4 @stage10
  Scenario: The detail page lists the parameters used
    Given I am viewing the gallery at the "small" size
    And I have turned grayscale on
    And I have set the blur to 6
    When I select the second image
    Then the page shows the image identifier 2
    And the page shows the size "large"
    And the page shows that grayscale is on
    And the page shows the blur value 6

  @F4_4 @stage10
  Scenario: The parameters panel reports defaults when nothing is chosen
    When I open the detail page for image 5
    Then the page shows the image identifier 5
    And the page shows the size "large"
    And the page shows that grayscale is off
    And the page shows the blur value 0

  @F4_1 @F2_3 @stage10
  Scenario: Returning to the gallery keeps my place and my filters
    Given I am viewing large grayscale images with blur 4
    When I open page 3 of the gallery
    And I select the first image
    And I follow the link back to the gallery
    Then the page shows images 21 to 30
    And the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 4

  # F4.4 amended — the panel is now the control surface as well as the report.
  # These are about what the page does when *asked*, where the scenarios above
  # are about what it does on arrival.
  # See docs/adr/0007-detail-view-size.md § Amendment.
  @F4_4 @stage11
  Scenario: The detail page offers controls for every parameter it reports
    When I open the detail page for image 7
    Then the page offers a control for the size
    And the page offers a control for grayscale
    And the page offers a control for the blur

  @F4_4 @stage11
  Scenario Outline: Choosing a size on the detail page
    When I open the detail page for image 7
    And I choose the "<size>" size on the detail page
    Then the image is rendered at size "<size>"
    And the page shows the size "<size>"

    Examples: Including sizes smaller than the page opened at
      | size   |
      | small  |
      | medium |
      | large  |

  @F4_4 @stage11
  Scenario: Turning grayscale on from the detail page
    When I open the detail page for image 7
    And I turn grayscale on from the detail page
    Then the image is rendered in grayscale
    And the page shows that grayscale is on

  @F4_4 @stage11
  Scenario: Changing the blur from the detail page
    When I open the detail page for image 7
    And I set the blur to 6 on the detail page
    Then the image is rendered with blur 6
    And the page shows the blur value 6

  # The panel reports what was used, and it is now the thing that set it — so
  # the two must agree after a change, not only on arrival.
  @F4_4 @stage11
  Scenario: The panel reports a value the user chose here, not the one they arrived with
    Given I am viewing the gallery at the "small" size
    When I select the first image
    And I choose the "medium" size on the detail page
    Then the page shows the size "medium"
    And the image is rendered at size "medium"

  # A choice made on this page belongs to this page. Otherwise opening one
  # image at "small" would silently re-render the whole grid on return.
  @F4_1 @F4_4 @stage11
  Scenario: A size chosen on the detail page does not follow me back to the gallery
    Given I am viewing large grayscale images with blur 4
    When I select the first image
    And I choose the "small" size on the detail page
    And I follow the link back to the gallery
    Then the images are rendered at size "large"
    And the images are rendered in grayscale
    And the images are rendered with blur 4

  @F4_1 @stage9
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

  @F3_6 @F4_3 @stage10
  Scenario: An invalid filter on the detail page falls back and says so
    When I open the detail page for image 4 with blur "99"
    Then the response status is 200
    And the image has no blur applied
    And the page explains that "99" is not a valid blur
