import requests
import string
from collections import deque

class MealDBAPIClient:
    """Retrieve meal records from TheMealDB using the letter-based search API.

    TheMealDB exposes a search endpoint that returns meals whose names begin
    with a given letter. This wrapper collects those letter-based responses into
    a larger list that can be turned into Recipe objects later.
    """

    def __init__(self):
        """Initialize the client with the base endpoint shared by all requests."""
        self.base_url = "https://www.themealdb.com/api/json/v1/1/"

    def fetch_recipes_by_letter(self, letter):
        """Fetch all recipes whose names begin with a specific letter.

        Parameters:
            letter (str): Lowercase alphabet letter used in the API query.

        Returns:
            list: Recipe records returned by the API, or an empty list if no
                    recipes were found for that letter or if the request failed.
        """
        url = f"{self.base_url}search.php?f={letter}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('meals') or []

        except requests.exceptions.RequestException as e:
            print(f"API request failed for letter ({letter}): {e}")
            return []

    def fetch_all_recipes(self):
        """Fetch recipes for every lowercase alphabet letter.

        Returns:
            list: Combined list of all recipes retrieved from the API.
        """
        print("Starting to fetch all recipes from TheMealDB API...")
        all_meals = []
        for letter in string.ascii_lowercase:
            meals = self.fetch_recipes_by_letter(letter)
            all_meals.extend(meals)
        return all_meals

class Recipe:
    """Store the normalized fields needed to represent one recipe."""

    def __init__(self, json_data):
        """Build a Recipe object from one raw TheMealDB response.

        Parameters:
            json_data (dict): Raw meal record returned by TheMealDB.
        """
        # Keep only the fields that the rest of this program actually uses.
        self.id = json_data.get('idMeal') or 'Unknown ID'
        self.name = json_data.get('strMeal') or 'Unknown Meal'
        self.category = json_data.get('strCategory') or 'Unknown Category'
        self.instructions = json_data.get('strInstructions') or 'No instructions were provided.'

        # Normalize ingredient names so graph search works reliably.
        self.ingredients = self.extract_ingredients(json_data)

    def extract_ingredients(self, json_data):
        """Collect and normalize ingredient names from the raw API record.

        Parameters:
            json_data (dict): Raw meal record returned by TheMealDB.

        Returns:
            list: Lowercased ingredient names with blank values skipped and leading/trailing whitespace stripped.
        """
        clean_ingredients = []
        # Ingredient fields are stored in fixed slots from strIngredient1 to strIngredient20, so we scan each slot in order.
        for i in range(1, 21):
            ingredient_key = f'strIngredient{i}'
            ingredient = json_data.get(ingredient_key)
            if ingredient and ingredient.strip():
                clean_ingredients.append(ingredient.strip().lower())
        return clean_ingredients

    def __str__(self):
        """Return a compact, human-readable summary of the recipe."""
        return f"Meal: {self.name} | Category: {self.category} | Ingredients: {self.ingredients}"
        
    def print_full_recipe(self):
        """Print the recipe in a readable multi-line format.

        This method is for presentation only; it is meant to show one complete
        recipe with consistent spacing and labels.
        """
        # The separator makes it easier to visually distinguish one recipe from
        # surrounding terminal output.
        print(f"\n{'='*40}")
        print(f"Recipe Name: {self.name}")
        print(f"Category: {self.category}")
        print(f"Ingredients: {', '.join(self.ingredients)}")
        print(f"Instructions:\n{self.instructions}")
        print(f"{'='*40}\n")

class RecipeGraph:
    """Undirected graph that connects meals to ingredients.

    The graph uses an adjacency-list representation:
    - meal nodes connect to ingredient nodes
    - ingredient nodes connect back to meal nodes

    This structure makes ingredient search and meal comparison straightforward
    without needing a separate database layer.
    """

    def __init__(self):
        """Initialize an empty graph and a lookup table for full recipe data."""
        self.graph = {}
        self.recipe_catalog = {} 

    def add_node(self, node):
        """Add a node to the graph if it is not already present."""
        if node not in self.graph:
            self.graph[node] = []

    def add_edge(self, node1, node2):
        """Create a two-way connection between two graph nodes.

        Parameters:
            node1 (str): First node in the relationship.
            node2 (str): Second node in the relationship.
        """
        self.add_node(node1)
        self.add_node(node2)
        
        # Since this is an undirected graph, we add each node to the other's adjacency list.
        if node2 not in self.graph[node1]:
            self.graph[node1].append(node2)
        if node1 not in self.graph[node2]:
            self.graph[node2].append(node1)

    def add_recipe_to_graph(self, recipe_obj):
        """Add one recipe node and connect it to every ingredient node.

        Parameters:
            recipe_obj (Recipe): Normalized recipe object to insert into the
                graph and the recipe lookup table.
        """
        recipe_node = recipe_obj.name
        self.add_node(recipe_node)

        # Keep the full object so the program can print recipe details later.
        self.recipe_catalog[recipe_node] = recipe_obj

        # Each ingredient becomes a neighbor of the meal node.
        for ingredient in recipe_obj.ingredients:
            self.add_edge(recipe_node, ingredient)

    def search_multiple_ingredients(self, target_ingredients):
        """Return recipes that contain every ingredient in the input list.

        Parameters:
            target_ingredients (list[str]): Ingredient names to search for.

        Returns:
            list: Meal names that are connected to every requested ingredient.
        """
        if not target_ingredients:
            return []

        # Start with the meals linked to the first ingredient in the list.
        base_ingredient = target_ingredients[0].strip().lower()
        if base_ingredient in self.graph:
            matching_recipes = list(self.graph[base_ingredient])
        else:
            return []

        # Each additional ingredient narrows the candidate set further.
        for next_ingredient in target_ingredients[1:]:
            next_ingredient = next_ingredient.strip().lower()
            # If the next ingredient is in the graph, we filter the current matches to keep only those that are also linked to this new ingredient.
            if next_ingredient in self.graph:
                filtered_matches = []
                recipes_with_next_ingredient = self.graph[next_ingredient]
                # We loop through the current matches and keep only those that are also linked to the next ingredient.
                for candidate_recipe in matching_recipes:
                    if candidate_recipe in recipes_with_next_ingredient:
                        filtered_matches.append(candidate_recipe)
                # After filtering, we update the list of matching recipes to reflect the new ingredient constraint.
                matching_recipes = filtered_matches
                # If at any point the list of matches becomes empty, we can stop early since no recipe can satisfy all ingredient requirements.
                if not matching_recipes:
                    break
            else:
                # If an ingredient is absent from the graph, no recipe can match.
                return []

        return matching_recipes

    def get_recipe_details(self, recipe_name):
        """Look up the full Recipe object for a meal name.

        Parameters:
            recipe_name (str): Meal name used as the lookup key.

        Returns:
            Recipe | None: Matching Recipe object when it exists, otherwise None.
        """
        # This lookup lets the program recover full recipe details without
        # reconstructing them from the graph structure.
        return self.recipe_catalog.get(recipe_name)

    def compare_two_meals(self, meal1_name, meal2_name):
        """Return ingredient names that appear in both meals.

        Parameters:
            meal1_name (str): First meal name to compare.
            meal2_name (str): Second meal name to compare.

        Returns:
            list: Ingredient names shared by both meals.
        """
        # Validate both names before reading the adjacency lists.
        if meal1_name not in self.graph or meal2_name not in self.graph:
            return []
        if meal1_name not in self.recipe_catalog or meal2_name not in self.recipe_catalog:
            return []
        # The graph structure allows us to directly access the ingredient lists for each meal without needing to parse the full recipe objects.
        ingredients_meal1 = self.graph[meal1_name]
        ingredients_meal2 = self.graph[meal2_name]

        shared_ingredients = []

        # Use a simple loop instead of set operations so the comparison logic is
        # easy to follow for someone reading the code for the first time.
        for ingredient in ingredients_meal1:
            if ingredient in ingredients_meal2:
                shared_ingredients.append(ingredient)

        return shared_ingredients
    
    def get_top_ingredients(self, top_n=10):
        """Rank ingredients by the number of recipes they appear in.

        Parameters:
            top_n (int): The number of top ingredients to return.

        Returns:
            list: A list of tuples containing (ingredient_name, usage_count).
        """
        ingredient_counts = []

        # loop through all nodes in the graph and identify which ones are ingredients by checking if they are not in the recipe_catalog.
        for node in self.graph:
            # We want to filter out "recipe nodes" and only count "ingredient nodes".
            # Since all recipes exist in recipe_catalog, anything not in the catalog is an ingredient!
            if node not in self.recipe_catalog:
                # In the Graph, the number of connections (Degree) is the number of times it appears
                usage_count = len(self.graph[node])
                # We store the count along with the ingredient name so we can sort by count later.
                ingredient_counts.append((usage_count, node))

        ingredient_counts.sort(key=lambda x: (-x[0], x[1]))  # Sort by count descending, then alphabetically.

        # Extract just the top N ingredients and their counts into a new list for the final output.
        top_ingredients = []
        for count, name in ingredient_counts[:top_n]:
            top_ingredients.append((name, count))

        return top_ingredients
    
    def find_shortest_path(self, start_ingredient, end_ingredient, exclude_nodes=None):
        """Find the shortest ingredient-to-ingredient path in the recipe graph.

        The search uses breadth-first search over the bipartite meal/ingredient
        graph, so the returned path alternates between ingredient and meal nodes.
        Optional excluded nodes are ignored during traversal unless they are one
        of the start or end ingredients.

        Parameters:
            start_ingredient (str): Ingredient name to start from.
            end_ingredient (str): Ingredient name to search for.
            exclude_nodes (iterable[str] | None): Ingredient nodes to skip while searching.

        Returns:
            list: [int, list[str]] when a connection exists, otherwise [-1, []].
        """

        # Normalize inputs to match how ingredient nodes are stored in the graph.
        start_node = start_ingredient.strip().lower()
        end_node = end_ingredient.strip().lower()

        # Initialize exclude_nodes to an empty set if not provided.
        # If provided, convert all items to lowercase to ensure accurate matching.
        if exclude_nodes is None:
            exclude_nodes = set()
        else:
            exclude_nodes = {node.strip().lower() for node in exclude_nodes}
            exclude_nodes -= {start_node, end_node}

        # Early exit if either endpoint does not exist in the graph.
        if start_node not in self.graph or end_node not in self.graph:
            return [-1, []]

        # Trivial case: same start and end ingredient means zero distance.
        if start_node == end_node:
            return [0, [start_node]]

        # Standard BFS setup.
        # queue stores nodes to visit in shortest-path order.
        queue = deque([start_node])
        # visited prevents revisiting nodes and cycles.
        visited = {start_node}
        # path_dict maps each discovered node to its predecessor.
        path_dict = {start_node: None}

        # Expand the search level by level from the start ingredient.
        while queue:
            current = queue.popleft()

            # Explore every neighbor connected to the current node.
            for neighbor in self.graph[current]:
                # Skip this neighbor if it is in the exclusion list (e.g., salt, water).
                # This forces the algorithm to find alternative, more interesting paths.
                if neighbor in exclude_nodes:
                    continue
                # Only consider neighbors that haven't been visited yet to avoid cycles and redundant paths.
                if neighbor not in visited:
                    visited.add(neighbor)
                    path_dict[neighbor] = current

                    # Stop early when we reach the target and rebuild the path.
                    if neighbor == end_node:
                        path = []
                        step = end_node
                        # Follow predecessor links backward to the start node.
                        while step is not None:
                            path.append(step)
                            step = path_dict[step]
                        # Reverse because we reconstructed from end -> start.
                        path.reverse()

                        # Path alternates ingredient/meal nodes.
                        # Dividing by 2 gives ingredient-to-ingredient hop count.
                        distance = len(path) // 2
                        return [distance, path]
                    # Continue BFS by queueing newly discovered nodes.
                    queue.append(neighbor)
        # No connection found between the two ingredient nodes.
        return [-1, []]

    def __str__(self):
        """Return a short summary of the graph contents."""
        return f"Graph has {len(self.graph)} nodes and indexes {len(self.recipe_catalog)} full recipes."

class RecipeRecommender:
    """Recommendation engine that ranks meals by pantry ingredient overlap.

    This class uses the existing recipe catalog (meal name -> Recipe object)
    to score recipes against ingredients the user already has.

    Ranking strategy:
    - more matched ingredients ranks higher
    - fewer missing ingredients ranks higher when match counts tie
    - alphabetical meal name is used as a final tie-breaker

    The class also supports an optional excluded-ingredients filter so users
    can avoid recipes containing specific items.
    """
    def __init__(self, recipe_catalog):
        """Initialize the recommender with a reference to the full recipe catalog."""
        self.recipe_catalog = recipe_catalog

    def recommend_recipes_by_pantry(self, available_ingredients, excluded_ingredients=None, top_n=10):
        """Recommend recipes based on ingredients the user already has.

        Parameters:
            available_ingredients (list[str]): Ingredients the user has on hand.
            excluded_ingredients (list[str] | None): Ingredients the user wants to avoid.
            top_n (int): Maximum number of recommendations to return.

        Returns:
            list[dict]: Ranked recipe recommendations. Each item contains:
                - name
                - matched_ingredients
                - missing_ingredients
                - matched_count
                - missing_count
        """
        if not available_ingredients:
            return []

        available_set = {ingredient.strip().lower() for ingredient in available_ingredients}
        excluded_set = {ingredient.strip().lower() for ingredient in (excluded_ingredients or [])}

        recommendations = []

        for recipe_name, recipe_obj in self.recipe_catalog.items():
            recipe_ingredients = set(recipe_obj.ingredients)

            # Skip recipes containing any excluded ingredient.
            if recipe_ingredients & excluded_set:
                continue

            matched_ingredients = sorted(recipe_ingredients & available_set)
            missing_ingredients = sorted(recipe_ingredients - available_set)

            # Only recommend recipes that match at least one available ingredient.
            if matched_ingredients:
                recommendations.append({
                    "name": recipe_name,
                    "matched_ingredients": matched_ingredients,
                    "missing_ingredients": missing_ingredients,
                    "matched_count": len(matched_ingredients),
                    "missing_count": len(missing_ingredients),
                })

        recommendations.sort(
            key=lambda item: (-item["matched_count"], item["missing_count"], item["name"])
        )

        return recommendations[:top_n]


# Display Functions

def display_ingredient_search(graph, ingredients):
    print(f"\n--- Search results for: {ingredients} ---")
    results = graph.search_multiple_ingredients(ingredients)
    if results:
        for r in results:
            print(f"- {r}")

        # Show the details of the first result as an example of how to use the recipe catalog.
        print(f"\n[Detail View: {results[0]}]")
        recipe = graph.get_recipe_details(results[0])
        if recipe:
            print(f"Category: {recipe.category}")
            print(f"Ingredients: {', '.join(recipe.ingredients)}")
            print(f"Instructions: {recipe.instructions[:200]}...")
    else:
        print("No recipes found.")

def display_comparison(graph, meal1, meal2):
    print(f"\n--- Comparison: {meal1} vs {meal2} ---")
    shared = graph.compare_two_meals(meal1, meal2)
    if shared:
        print(f"Shared ingredients: {', '.join(shared)}")
    else:
        print("No shared ingredients.")

def display_rankings(graph):
    print("\n--- Top 10 Ingredients ---")
    top = graph.get_top_ingredients(10)
    for i, (name, count) in enumerate(top, 1):
        print(f"{i}. {name} ({count} recipes)")

def display_path(graph, start, end):
    print(f"\n--- Shortest Path: {start} to {end} ---")
    result = graph.find_shortest_path(start, end)
    distance, path = result
    if path:
        print(f"Distance: {distance}")
        print(" -> ".join(path))
    else:
        print("No path found.")

def display_pantry_recommendations(recommender, available, excluded=None, top_n=5):
    print(f"\n--- Pantry Recommendations for: {available} ---")
    if excluded:
        print(f"Avoiding: {excluded}")

    results = recommender.recommend_recipes_by_pantry(available, excluded_ingredients=excluded, top_n=top_n)

    if results:
        for item in results:
            print(f"- {item['name']}")
            print(f"  Matched: {', '.join(item['matched_ingredients'])}")
            print(f"  Missing: {', '.join(item['missing_ingredients']) if item['missing_ingredients'] else 'None'}")
            print(f"  Score: {item['matched_count']} matched, {item['missing_count']} missing")
    else:
        print("No recommendations found.")


def main():
    """Run the command-line menu for exploring the recipe graph features."""

    # Fetch all recipes from the API and build the graph.
    client = MealDBAPIClient()
    meals_data = client.fetch_all_recipes()

    if not meals_data:
        return

    graph = RecipeGraph()
    for data in meals_data:
        graph.add_recipe_to_graph(Recipe(data))
    recommender = RecipeRecommender(graph.recipe_catalog)

    while True:
        print("\n1. Ingredient Search (ex: garlic, olive oil)")
        print("2. Compare Two Meals (ex: Mutabbaq vs Paella)")
        print("3. Top Ingredients Ranking")
        print("4. Shortest Path (ex: onion to garlic)")
        print("5. Pantry Recommendation")
        print("0. Exit")
        choice = input("\nSelect a mode: ").strip()

        if choice == "1":
            ings = input("Enter ingredients (comma-separated): ").split(",")
            ingredient_list = [i.strip() for i in ings if i.strip()]
            display_ingredient_search(graph, ingredient_list)
        elif choice == "2":
            meal1 = input("First meal (ex: Mutabbaq): ").strip()
            meal2 = input("Second meal (ex: Paella): ").strip()
            display_comparison(graph, meal1, meal2)
        elif choice == "3":
            display_rankings(graph)
        elif choice == "4":
            start = input("Start ingredient (ex: onion): ").strip()
            end = input("End ingredient (ex: garlic): ").strip()
            display_path(graph, start, end)
        elif choice == "5":
            ings = input("Ingredients you have (comma-separated): ").split(",")
            excluded = input("Ingredients to avoid (comma-separated, optional): ").split(",")

            available_list = [i.strip() for i in ings if i.strip()]
            excluded_list = [i.strip() for i in excluded if i.strip()]

            display_pantry_recommendations(
                recommender,
                available_list,
                excluded=excluded_list
            )
        elif choice == "0":
            break
        else:
            print("Invalid choice. Please select a valid mode.")


if __name__ == "__main__":
    main()

