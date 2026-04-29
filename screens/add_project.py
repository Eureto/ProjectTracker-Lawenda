from kivymd.uix.screen import MDScreen

class AddProjectScreen(MDScreen):
    def save_project(self, project_name, image_url, motivational_quote):
        print(f"Saving project: {project_name}, {image_url}, {motivational_quote}")
        # Here you would typically save the project data
        # For now, just navigate back to the home screen
        self.manager.current = 'home'
