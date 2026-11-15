import unittest
from recipe_graph import Recipe, RecipeGraph, RecipeRecommender

class TestRecipeGraph(unittest.TestCase):
    """Test suite for the Recipe, RecipeGraph, and RecipeRecommender classes.

    This suite verifies that meal data is correctly parsed into graph nodes
    and edges, and ensures that all graph algorithms, including search,
    comparison, ranking, shortest path, and recommendations, work correctly
    using a small hand-crafted test fixture.
    """

    def setUp(self):
        """Create a reusable graph fixture with three small sample recipes.

        The fixture is designed so tests can verify both positive and negative
        cases:
        - overlapping ingredients (for intersections and ranking)
        - unique ingredients (for graph edge checks)
        - connected ingredients through meal nodes (for shortest-path tests)
        """
        self.graph = RecipeGraph()

        recipe1 = Recipe({'idMeal': '1', 'strMeal': 'Apple Pie', 'strCategory': 'Dessert',
                          'strInstructions': 'test instructions',
                          'strIngredient1': 'Apple', 'strIngredient2': 'Sugar'})

        recipe2 = Recipe({'idMeal': '2', 'strMeal': 'Garlic Bread', 'strCategory': 'Side',
                          'strInstructions': 'test instructions',
                          'strIngredient1': 'Garlic', 'strIngredient2': 'Butter', 'strIngredient3': 'Sugar'})

        recipe3 = Recipe({'idMeal': '3', 'strMeal': 'Garlic Soup', 'strCategory': 'Soup',
                          'strInstructions': 'test instructions',
                          'strIngredient1': 'Garlic', 'strIngredient2': 'Water'})

        self.graph.add_recipe_to_graph(recipe1)
        self.graph.add_recipe_to_graph(recipe2)
        self.graph.add_recipe_to_graph(recipe3)
        self.recommender = RecipeRecommender(self.graph.recipe_catalog)

    def test_recipe_cleaning(self):
        """Ensure Recipe strips whitespace, skips blanks, and lowercases ingredients."""
        dirty_json = {
            'idMeal': '99',
            'strMeal': 'Test Dish',
            'strCategory': 'Test',
            'strInstructions': 'test instructions',
            'strIngredient1': 'Apple',
            'strIngredient2': ' Sugar ',
            'strIngredient3': '',
            'strIngredient4': None
        }
        r = Recipe(dirty_json)

        # Only the two valid ingredients should be retained.
        self.assertEqual(len(r.ingredients), 2)

        # Ingredients should be lowercased and whitespace removed.
        self.assertIn('apple', r.ingredients)
        self.assertIn('sugar', r.ingredients)

    def test_graph_building(self):
        """Ensure meal and ingredient nodes are linked in both directions."""
        # Meal -> ingredient edge should exist after graph construction.
        self.assertIn('apple', self.graph.graph['Apple Pie'])

        # Ingredient -> meal edge should also exist because the graph is undirected.
        self.assertIn('Apple Pie', self.graph.graph['sugar'])

    def test_search_multiple_ingredients(self):
        """Verify ingredient search returns matching meals and handles misses."""
        # Searching for a real ingredient should return all meals containing it.
        garlic_recipes = self.graph.search_multiple_ingredients(['garlic'])
        self.assertIn('Garlic Bread', garlic_recipes)
        self.assertIn('Garlic Soup', garlic_recipes)

        # Searching for an ingredient absent from the graph should return no matches.
        fake_recipes = self.graph.search_multiple_ingredients(['dragon fruit'])
        self.assertEqual(fake_recipes, [])

        # Searching for multiple ingredients should return only meals that contain all of them.
        # Garlic Soup has garlic but not butter, so it should be excluded.
        both = self.graph.search_multiple_ingredients(['garlic', 'butter'])
        self.assertIn('Garlic Bread', both)
        self.assertNotIn('Garlic Soup', both)
    
    def test_search_multiple_ingredients_empty_input(self):
        """Searching with no ingredients should return an empty list."""
        self.assertEqual(self.graph.search_multiple_ingredients([]), [])

    def test_get_recipe_details(self):
        """Ensure recipe detail lookup returns objects when present and None when absent."""
        recipe = self.graph.get_recipe_details('Apple Pie')
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.name, 'Apple Pie')

        missing_recipe = self.graph.get_recipe_details('Nonexistent Dish')
        self.assertIsNone(missing_recipe)

    def test_compare_two_meals(self):
        """Check shared-ingredient comparison between two meal nodes."""
        # Garlic appears in both meals and should be detected as shared.
        shared_ingredients = self.graph.compare_two_meals('Garlic Bread', 'Garlic Soup')
        self.assertIn('garlic', shared_ingredients)

        # Butter exists only in Garlic Bread and should not appear as shared.
        self.assertNotIn('butter', shared_ingredients)

        # Passing a meal name that does not exist in the graph should return an empty list.
        invalid = self.graph.compare_two_meals('Nonexistent Dish', 'Garlic Soup')
        self.assertEqual(invalid, [])

    def test_get_top_ingredients(self):
        """Confirm ingredient ranking reflects recipe occurrence counts."""
        # Request the top three ingredients ranked by number of connected meals.
        top_ingredients = self.graph.get_top_ingredients(3)

        first_place_name, first_place_count = top_ingredients[0]
        self.assertEqual(first_place_count, 2)

        # Both sugar and garlic appear in two recipes, so either is a valid top result.
        self.assertIn(first_place_name, ['sugar', 'garlic'])
    
    def test_get_top_ingredients_edge_cases(self):
        """Check ranking behavior for empty graphs and oversized top_n requests."""
        empty_graph = RecipeGraph()
        self.assertEqual(empty_graph.get_top_ingredients(5), [])

        top_ingredients = self.graph.get_top_ingredients(10)
        self.assertEqual(len(top_ingredients), 5)
        ingredient_names = [name for name, _ in top_ingredients]
        self.assertIn('garlic', ingredient_names)
        self.assertIn('sugar', ingredient_names)

    def test_find_shortest_path(self):
        """Validate BFS shortest path and distance between two ingredients."""
        # Expected route in this fixture:
        # apple -> Apple Pie -> sugar -> Garlic Bread -> garlic
        # which corresponds to 2 ingredient-to-ingredient hops.
        distance, path = self.graph.find_shortest_path('apple', 'garlic')

        # The computed ingredient-hop distance should match the known fixture path.
        self.assertEqual(distance, 2)

        # Path endpoints should preserve the requested start and end ingredients.
        self.assertEqual(path[0], 'apple')
        self.assertEqual(path[-1], 'garlic')

        # When start and end are the same ingredient, the distance should be zero.
        dist_same, path_same = self.graph.find_shortest_path('garlic', 'garlic')
        self.assertEqual(dist_same, 0)
        self.assertEqual(path_same, ['garlic'])

        # Searching for a path to a non-existent ingredient should return [-1, []].
        result_invalid = self.graph.find_shortest_path('apple', 'unicorn tears')
        self.assertEqual(result_invalid, [-1, []])

        # Testing the "exclude specific nodes" advanced feature.
        # Excluding 'sugar' should break the path between 'apple' and 'garlic' because 'sugar' is the only bridge in the fixture.
        path_excluded = self.graph.find_shortest_path('apple', 'garlic', exclude_nodes={'sugar'})

        # The distance should be -1 (meaning the path is broken/not found).
        self.assertEqual(path_excluded[0], -1) 
        # The path list should be completely empty.
        self.assertEqual(len(path_excluded[1]), 0)

    def test_recommend_recipes_by_pantry(self):
        """Recommend recipes based on available ingredients and rank them sensibly."""
        results = self.recommender.recommend_recipes_by_pantry(['garlic', 'sugar'], top_n=5)

        self.assertGreater(len(results), 0)

        # Garlic Bread should be a strong match because it contains both garlic and sugar.
        self.assertEqual(results[0]['name'], 'Garlic Bread')
        self.assertEqual(results[0]['matched_count'], 2)
        self.assertIn('butter', results[0]['missing_ingredients'])

        # Garlic Soup should also appear because it matches garlic.
        recipe_names = [item['name'] for item in results]
        self.assertIn('Garlic Soup', recipe_names)

    def test_recommend_recipes_by_pantry_edge_cases(self):
        """Check pantry recommendation behavior for exclusions and empty input."""
        # Excluding butter should remove Garlic Bread from results.
        results = self.recommender.recommend_recipes_by_pantry(
            ['garlic', 'sugar'],
            excluded_ingredients=['butter'],
            top_n=5
        )
        recipe_names = [item['name'] for item in results]
        self.assertNotIn('Garlic Bread', recipe_names)
        self.assertIn('Garlic Soup', recipe_names)

        # Empty pantry input should return no recommendations.
        empty_results = self.recommender.recommend_recipes_by_pantry([])
        self.assertEqual(empty_results, [])


if __name__ == '__main__':
    unittest.main()
