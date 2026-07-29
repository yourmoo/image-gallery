Feature: Image gallery and pagination
  As someone browsing the gallery
  I want a grid of images I can page through
  So that I can see the whole collection without one enormous page

  Covers F1.1-F1.3 and F2.1-F2.7. See docs/core-features.md for the
  requirement IDs and the decisions behind the invalid-page behaviour.

  Background:
    Given the gallery is available
    And the collection holds 100 images

  @F1_1 @F1_3 @F2_4 @stage1
  Scenario: The gallery shows a grid of images
    When I open the gallery
    Then the response status is 200
    And the page shows 10 images in a grid

  @F2_6 @stage1
  Scenario: The first page shows the first ten images
    When I open the gallery
    Then the page shows images 1 to 10

  @F2_6 @stage3
  Scenario: The second page continues where the first ended
    When I open page 2 of the gallery
    Then the page shows images 11 to 20

  # F2.7 — one browser call for the page's metadata, then one image request
  # per tile. Images are fetched when the browser asks for them, not while
  # the metadata call is being served. See docs/adr/0017-image-fetch-timing.md.
  @F2_7 @stage1
  Scenario: The page metadata is one call that reaches no further
    When I open the gallery
    Then 1 gallery data request is made
    And no upstream image requests are made

  @F2_7 @F1_2 @stage2
  Scenario: A page is composed from one upstream call per image
    When I open the gallery
    And the images have finished loading
    Then 10 upstream image requests are made

  # F2.5 — the count must be a real control on the page, not merely a
  # query parameter a test can set.
  @F2_5 @stage4
  Scenario: The page offers a control for choosing the image count
    When I open the gallery
    Then the page offers image counts of 10, 20 and 50

  @F2_5 @stage4
  Scenario Outline: Choosing an image count changes how many images appear
    When I choose to see <count> images per page
    Then the page shows <count> images in a grid

    Examples:
      | count |
      | 10    |
      | 20    |
      | 50    |

  @F2_1 @stage3
  Scenario: Page state is carried in the URL
    When I open page 3 of the gallery
    Then the page number in the address is 3
    And the page shows images 21 to 30

  # F2.3 — the most easily broken pagination requirement.
  @F2_3 @stage3
  Scenario: Pagination links keep the active size and filters
    Given I am viewing large grayscale images with blur 4
    When I open the gallery
    Then the link to the next page keeps size "large"
    And the link to the next page keeps grayscale enabled
    And the link to the next page keeps blur 4

  @F2_1 @stage3
  Scenario: The last page is the end of the collection
    When I open page 10 of the gallery
    Then the page shows images 91 to 100
    And there is no link to a next page

  @F2_1 @stage3
  Scenario: The first page has no previous page
    When I open the gallery
    Then there is no link to a previous page

  # F2.2 — invalid pages recover rather than dead-end. The notice travels
  # in the URL because there is no database, so no sessions and no
  # django.contrib.messages.
  @F2_2 @stage5
  Scenario Outline: An invalid page sends me to page 1 with an explanation
    When I open the gallery at page "<page>"
    Then I am redirected to page 1
    And the page explains that the requested page was not valid
    And the page shows images 1 to 10

    Examples: Not a number
      | page   |
      | abc    |
      |        |

    Examples: Out of range
      | page   |
      | 0      |
      | -5     |
      | 999    |

  @F2_2 @stage5
  Scenario: A valid page is not redirected
    When I open page 2 of the gallery
    Then the response status is 200
    And no validation message is shown

  # F5.5 — cached while the app is running. Observable because a second
  # request must not reach upstream again.
  @F5_5 @stage6
  Scenario: Repeating a request does not call upstream again
    Given I have already opened the gallery
    When I open the gallery again
    And the images have finished loading
    Then no further upstream image requests are made
    And the page shows images 1 to 10

  # Resilience — failure is handled per image, so a page renders what it can.
  # Each tile fails on its own because each is its own request, and the grid
  # is already on screen when it happens. See docs/adr/0012-resilience-strategy.md.
  @resilience @stage6
  Scenario: A page still renders when some images are unavailable
    Given the gallery is unavailable for 3 of the images on page 1
    When I open the gallery
    Then the response status is 200
    And the page shows 10 images in a grid
    When the images have finished loading
    Then 7 images are shown
    And 3 images are shown as unavailable
    And the page explains that some images could not be loaded

  @resilience @stage6
  Scenario: A working image is unaffected by a neighbour that fails
    Given the gallery is unavailable for 3 of the images on page 1
    When I open the gallery
    And the images have finished loading
    Then the 7 available images are rendered at size "medium"

  @resilience @F5_5 @stage6
  Scenario: A previously seen image is still shown when the gallery is unavailable
    Given I have already opened the gallery
    And the gallery becomes unavailable
    When I open the gallery again
    And the images have finished loading
    Then the response status is 200
    And the page shows images 1 to 10
    And no image is shown as unavailable

  @resilience @stage6
  Scenario: Images never seen before are shown as unavailable
    Given the gallery is unavailable
    When I open the gallery
    Then the response status is 200
    And the page shows 10 images in a grid
    When the images have finished loading
    Then every image is shown as unavailable
    And the page explains that some images could not be loaded

  # The grid is on screen before any image request completes, so a slow
  # upstream delays tiles filling in — it never delays the page itself.
  @resilience @stage6
  Scenario: A slow gallery does not hold the page open indefinitely
    Given the gallery does not respond in time
    When I open the gallery
    Then the response status is 200
    And the page shows 10 images in a grid
    When the images have finished loading
    Then every image is shown as unavailable

  @resilience @stage6
  Scenario: The grid appears before the images do
    Given the gallery does not respond in time
    When I open the gallery
    Then the page shows 10 images in a grid
    And I did not have to wait for the images
